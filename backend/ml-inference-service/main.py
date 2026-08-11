"""
ML Inference Service
Provides low-latency model inference for anomaly detection and failure prediction
"""

import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
import numpy as np

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.config import settings
from shared.logging_config import setup_logging
from shared.auth import require_roles
from shared.metrics import setup_metrics
from shared.tracing import setup_tracing
from rul_model import rul_model_manager
from federated_learning import (
    federated_coordinator,
    train_local_linear_model,
    WEIGHT_DIM,
    FEATURE_NAMES,
)

# Setup logging
logger = setup_logging("ml-inference-service")

# Setup logging
logger = setup_logging("ml-inference-service")

# Import advanced LSTM model
try:
    from advanced_lstm_model import AdvancedLSTMModel, get_well_model

    ADVANCED_LSTM_AVAILABLE = True
except ImportError:
    ADVANCED_LSTM_AVAILABLE = False
    logger.warning("Advanced LSTM model not available")

try:
    from prometheus_client import Counter, Histogram

    METRICS_ENABLED = True
    INFERENCE_REQUESTS = Counter(
        "ml_inference_requests_total",
        "Total inference requests",
        ["model_type"],
    )
    INFERENCE_ERRORS = Counter(
        "ml_inference_errors_total",
        "Total inference errors",
        ["model_type", "reason"],
    )
    INFERENCE_LATENCY = Histogram(
        "ml_inference_latency_seconds",
        "Inference latency in seconds",
        ["model_type"],
    )
except ImportError:  # pragma: no cover - dependency optional at runtime
    METRICS_ENABLED = False
    INFERENCE_REQUESTS = INFERENCE_ERRORS = INFERENCE_LATENCY = None  # type: ignore

# Import MLflow integration
try:
    from mlflow_integration import get_mlflow_manager

    MLFLOW_AVAILABLE = True
except ImportError:
    logger.warning("MLflow not available, using mock models")
    MLFLOW_AVAILABLE = False

app = FastAPI(title="OGIM ML Inference Service", version="1.0.0")
setup_metrics(app, "ml-inference-service")
setup_tracing(app, "ml-inference-service")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure model storage path is aligned with shared settings
os.environ.setdefault("MODEL_STORAGE_PATH", settings.MODEL_STORAGE_PATH)

# MLflow manager
mlflow_manager = None
MODEL_TYPE_TO_REGISTRY = {
    "anomaly_detection": "anomaly-detection",
    "failure_prediction": "failure-prediction",
    "time_series_forecast": "time-series-forecast",
}


class InferenceRequest(BaseModel):
    sensor_id: str
    features: Dict[str, float]
    model_type: str = "anomaly_detection"  # or "failure_prediction"
    model_version: Optional[int] = None


class InferenceResponse(BaseModel):
    sensor_id: str
    model_type: str
    prediction: float
    probability: float
    anomaly_score: Optional[float] = None
    failure_probability: Optional[float] = None
    model_version: Optional[int] = None
    deployment_variant: Optional[str] = None
    timestamp: datetime


class TimeSeriesForecastRequest(BaseModel):
    sensor_id: str
    historical_data: List[float]
    forecast_steps: int = 1


class TimeSeriesForecastResponse(BaseModel):
    sensor_id: str
    predictions: List[float]
    forecast_steps: int
    sequence_length: int
    confidence: float
    timestamp: datetime
    confidence_lower: Optional[List[float]] = None
    confidence_upper: Optional[List[float]] = None
    model_type: Optional[str] = None


class TrainLSTMRequest(BaseModel):
    well_name: str
    time_series_data: List[float]
    model_type: str = "stacked_lstm"  # stacked_lstm, bidirectional, attention
    sequence_length: int = 60
    forecast_horizon: int = 24
    epochs: int = 100
    batch_size: int = 32
    validation_split: float = 0.2


class TrainLSTMResponse(BaseModel):
    well_name: str
    model_type: str
    training_status: str
    metrics: Dict[str, float]
    epochs_trained: int
    message: str


class ModelCompareRequest(BaseModel):
    baseline_version: int
    candidate_version: int


class ABTestConfigRequest(BaseModel):
    baseline_version: int
    candidate_version: int
    candidate_weight: float = 0.5
    seed: int = 42


class DriftBaselineRequest(BaseModel):
    features: List[Dict[str, float]]

    @field_validator("features", mode="before")
    @classmethod
    def normalize_features(cls, value: Any) -> List[Dict[str, float]]:
        if isinstance(value, dict):
            return [value]
        return value


class DriftDetectRequest(BaseModel):
    features: List[Dict[str, float]]
    threshold: float = 0.5

    @field_validator("features", mode="before")
    @classmethod
    def normalize_features(cls, value: Any) -> List[Dict[str, float]]:
        if isinstance(value, dict):
            return [value]
        return value


class FederatedNodeUpdateRequest(BaseModel):
    well_name: str
    location: str
    local_weights: List[float]
    local_accuracy: float
    data_size: int


class FederatedLocalTrainRequest(BaseModel):
    well_name: str
    location: str
    samples: List[Dict[str, float]]
    labels: List[float]


class FederatedAggregateRequest(BaseModel):
    min_nodes: int = 2


@app.on_event("startup")
async def startup_event():
    """Initialize MLflow manager on startup"""
    global mlflow_manager
    logger.info("Starting ML inference service...")

    if MLFLOW_AVAILABLE:
        try:
            mlflow_manager = get_mlflow_manager(
                model_path=settings.MODEL_STORAGE_PATH,
                tracking_uri=settings.MLFLOW_TRACKING_URI,
            )
            load_results = mlflow_manager.load_registered_models()
            logger.info("Model load results: %s", load_results)
        except Exception as e:
            logger.error(f"Failed to initialize MLflow: {e}")
            logger.warning("Falling back to mock models")


# Mock ML models (fallback if MLflow unavailable)
def mock_anomaly_detection(features: Dict[str, float]) -> Dict[str, float]:
    """Mock anomaly detection model"""
    anomaly_score = 0.0
    for value in features.values():
        if value > 100 or value < -100:
            anomaly_score += 0.3
        elif abs(value) > 50:
            anomaly_score += 0.1

    anomaly_score = min(1.0, anomaly_score)
    is_anomaly = 1.0 if anomaly_score > 0.5 else 0.0

    return {
        "prediction": is_anomaly,
        "anomaly_score": anomaly_score,
        "probability": anomaly_score,
    }


def mock_failure_prediction(features: Dict[str, float]) -> Dict[str, float]:
    """Mock failure prediction model"""
    failure_prob = 0.0
    for value in features.values():
        if value > 200:
            failure_prob += 0.2
        elif value > 150:
            failure_prob += 0.1

    failure_prob = min(1.0, failure_prob)

    return {
        "prediction": failure_prob,
        "failure_probability": failure_prob,
        "probability": failure_prob,
    }


@app.post("/infer", response_model=InferenceResponse)
async def infer(request: InferenceRequest):
    """Perform model inference"""
    start_time = None
    if METRICS_ENABLED:
        INFERENCE_REQUESTS.labels(request.model_type).inc()
        start_time = time.perf_counter()

    try:
        selected_version = request.model_version
        deployment_variant = "default"
        if MLFLOW_AVAILABLE and mlflow_manager and request.model_version is None:
            (
                selected_version,
                deployment_variant,
            ) = mlflow_manager.resolve_model_for_request(
                request.model_type,
                request.sensor_id,
            )

        # Use MLflow models if available, otherwise fallback to mock
        if MLFLOW_AVAILABLE and mlflow_manager:
            if request.model_type == "anomaly_detection":
                result = mlflow_manager.predict_anomaly(
                    request.features, version=selected_version
                )
            elif request.model_type == "failure_prediction":
                result = mlflow_manager.predict_failure(
                    request.features, version=selected_version
                )
            elif request.model_type == "time_series_forecast":
                raise HTTPException(
                    status_code=400,
                    detail="Use /forecast endpoint for time series predictions",
                )
            else:
                raise HTTPException(
                    status_code=400, detail=f"Unknown model type: {request.model_type}"
                )
        else:
            # Fallback to mock models
            if request.model_type == "anomaly_detection":
                result = mock_anomaly_detection(request.features)
            elif request.model_type == "failure_prediction":
                result = mock_failure_prediction(request.features)
            elif request.model_type == "time_series_forecast":
                raise HTTPException(
                    status_code=400,
                    detail="Use /forecast endpoint for time series predictions",
                )
            else:
                raise HTTPException(
                    status_code=400, detail=f"Unknown model type: {request.model_type}"
                )

        logger.info(f"Inference completed for {request.sensor_id}")

        return InferenceResponse(
            sensor_id=request.sensor_id,
            model_type=request.model_type,
            prediction=result["prediction"],
            probability=result["probability"],
            anomaly_score=result.get("anomaly_score"),
            failure_probability=result.get("failure_probability"),
            model_version=selected_version,
            deployment_variant=deployment_variant,
            timestamp=datetime.utcnow(),
        )
    except RuntimeError as exc:
        logger.warning("Inference unavailable for %s: %s", request.model_type, exc)
        if METRICS_ENABLED:
            INFERENCE_ERRORS.labels(request.model_type, "unavailable").inc()
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as e:
        logger.error(f"Inference error: {e}")
        if METRICS_ENABLED:
            INFERENCE_ERRORS.labels(request.model_type, type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")
    finally:
        if METRICS_ENABLED and start_time is not None:
            duration = time.perf_counter() - start_time
            INFERENCE_LATENCY.labels(request.model_type).observe(duration)


@app.post("/batch_infer")
async def batch_infer(requests: List[InferenceRequest]):
    """Batch inference for multiple sensors"""
    results = []
    for req in requests:
        try:
            response = await infer(req)
            results.append(response.dict())
        except Exception as e:
            results.append({"error": str(e), "sensor_id": req.sensor_id})
    return {"results": results}


@app.post("/forecast", response_model=TimeSeriesForecastResponse)
async def forecast_time_series(request: TimeSeriesForecastRequest):
    """Perform time series forecasting using LSTM model"""
    start_time = None
    if METRICS_ENABLED:
        INFERENCE_REQUESTS.labels("time_series_forecast").inc()
        start_time = time.perf_counter()

    try:
        # Try advanced LSTM first
        if ADVANCED_LSTM_AVAILABLE:
            # Extract well name from sensor_id (assuming format: WELL-SENSOR)
            well_name = (
                request.sensor_id.split("-")[0]
                if "-" in request.sensor_id
                else "default"
            )
            model = get_well_model(well_name, model_type="stacked_lstm")

            if model.is_trained:
                historical_array = np.array(request.historical_data)
                result = model.predict(
                    historical_array, forecast_steps=request.forecast_steps
                )

                logger.info(f"Advanced LSTM forecast completed for {request.sensor_id}")

                return TimeSeriesForecastResponse(
                    sensor_id=request.sensor_id,
                    predictions=result["predictions"],
                    forecast_steps=result["forecast_steps"],
                    sequence_length=result["sequence_length"],
                    confidence=result["confidence"],
                    timestamp=datetime.utcnow(),
                    confidence_lower=result.get("confidence_lower"),
                    confidence_upper=result.get("confidence_upper"),
                    model_type=result.get("model_type"),
                )

        # Fallback to MLflow model
        if not (MLFLOW_AVAILABLE and mlflow_manager):
            raise HTTPException(
                status_code=503,
                detail="LSTM models not available. Please train a model first.",
            )

        result = mlflow_manager.predict_time_series(
            historical_data=request.historical_data,
            forecast_steps=request.forecast_steps,
        )

        logger.info(f"Time series forecast completed for {request.sensor_id}")

        return TimeSeriesForecastResponse(
            sensor_id=request.sensor_id,
            predictions=result["predictions"],
            forecast_steps=result["forecast_steps"],
            sequence_length=result["sequence_length"],
            confidence=result["confidence"],
            timestamp=datetime.utcnow(),
        )
    except ValueError as e:
        logger.warning("Invalid input for time series forecast: %s", e)
        if METRICS_ENABLED:
            INFERENCE_ERRORS.labels("time_series_forecast", "invalid_input").inc()
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.warning("Time series forecast unavailable: %s", e)
        if METRICS_ENABLED:
            INFERENCE_ERRORS.labels("time_series_forecast", "unavailable").inc()
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Time series forecast error: {e}")
        if METRICS_ENABLED:
            INFERENCE_ERRORS.labels("time_series_forecast", type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=f"Forecast error: {str(e)}")
    finally:
        if METRICS_ENABLED and start_time is not None:
            duration = time.perf_counter() - start_time
            INFERENCE_LATENCY.labels("time_series_forecast").observe(duration)


@app.post("/lstm/train", response_model=TrainLSTMResponse)
async def train_lstm_model(
    request: TrainLSTMRequest,
    _: Dict[str, Any] = Depends(require_roles({"system_admin", "data_engineer"})),
):
    """Train advanced LSTM model for a specific well"""
    if not ADVANCED_LSTM_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Advanced LSTM models not available. TensorFlow is required.",
        )

    try:
        # Get or create model for this well
        model = get_well_model(request.well_name, model_type=request.model_type)

        # Prepare data
        data_array = np.array(request.time_series_data).reshape(-1, 1)

        # Create sequences
        X, y = [], []
        seq_len = request.sequence_length
        forecast_horizon = request.forecast_horizon

        for i in range(len(data_array) - seq_len - forecast_horizon + 1):
            X.append(data_array[i : (i + seq_len)])
            y.append(data_array[i + seq_len : i + seq_len + forecast_horizon])

        X = np.array(X)
        y = np.array(y)

        if len(X) == 0:
            raise ValueError(
                f"Not enough data. Need at least {seq_len + forecast_horizon} points, "
                f"got {len(data_array)}"
            )

        # Update model parameters
        model.sequence_length = seq_len
        model.forecast_horizon = forecast_horizon

        # Train model
        metrics = model.train(
            X_train=X,
            y_train=y,
            epochs=request.epochs,
            batch_size=request.batch_size,
            validation_split=request.validation_split,
            verbose=0,
        )

        logger.info(f"LSTM model trained for well {request.well_name}: {metrics}")

        return TrainLSTMResponse(
            well_name=request.well_name,
            model_type=request.model_type,
            training_status="completed",
            metrics=metrics,
            epochs_trained=metrics.get("epochs_trained", request.epochs),
            message=f"Model trained successfully for {request.well_name}",
        )
    except ValueError as e:
        logger.warning(f"Invalid input for LSTM training: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"LSTM training error: {e}")
        raise HTTPException(status_code=500, detail=f"Training error: {str(e)}")


@app.get("/lstm/models")
async def list_lstm_models(
    _: Dict[str, Any] = Depends(
        require_roles({"system_admin", "data_engineer", "field_operator"})
    )
):
    """List all trained LSTM models"""
    if not ADVANCED_LSTM_AVAILABLE:
        return {"models": [], "message": "Advanced LSTM not available"}

    from advanced_lstm_model import _well_models

    models_info = []
    for key, model in _well_models.items():
        if model.is_trained:
            well_name, model_type = key.rsplit("_", 1)
            models_info.append(
                {
                    "well_name": well_name,
                    "model_type": model_type,
                    "sequence_length": model.sequence_length,
                    "forecast_horizon": model.forecast_horizon,
                    "is_trained": model.is_trained,
                }
            )

    return {"models": models_info, "count": len(models_info)}


@app.get("/models")
async def list_models():
    """List available models"""
    if not (MLFLOW_AVAILABLE and mlflow_manager):
        return {
            "models": [
                {
                    "type": "anomaly_detection",
                    "registry": None,
                    "loaded": False,
                    "status": "mock",
                },
                {
                    "type": "failure_prediction",
                    "registry": None,
                    "loaded": False,
                    "status": "mock",
                },
                {
                    "type": "time_series_forecast",
                    "registry": None,
                    "loaded": False,
                    "status": "mock",
                },
            ]
        }

    models = []
    for model_type, registry_name in MODEL_TYPE_TO_REGISTRY.items():
        info = mlflow_manager.get_model_info(registry_name)
        models.append(
            {
                "type": model_type,
                "registry": registry_name,
                "loaded": model_type in mlflow_manager.models,
                "status": "ready" if info else "missing",
                "info": info,
            }
        )

    return {"models": models}


@app.post("/models/{model_type}/train")
async def train_model(
    model_type: str,
    _: Dict[str, Any] = Depends(require_roles({"system_admin"})),
):
    """Trigger model training on demand."""
    if not (MLFLOW_AVAILABLE and mlflow_manager):
        raise HTTPException(status_code=503, detail="MLflow integration not available")

    if model_type == "anomaly_detection":
        mlflow_manager.train_anomaly_detection_model()
        mlflow_manager.load_model(MODEL_TYPE_TO_REGISTRY[model_type])
    elif model_type == "failure_prediction":
        mlflow_manager.train_failure_prediction_model()
        mlflow_manager.load_model(MODEL_TYPE_TO_REGISTRY[model_type])
    elif model_type == "time_series_forecast":
        mlflow_manager.train_time_series_model()
        mlflow_manager.load_model(MODEL_TYPE_TO_REGISTRY[model_type])
    else:
        raise HTTPException(status_code=400, detail=f"Unknown model type: {model_type}")

    return {"message": f"{model_type} model training started"}


@app.post("/models/reload")
async def reload_models(
    _: Dict[str, Any] = Depends(require_roles({"system_admin"})),
):
    """Reload registered models from MLflow."""
    if not (MLFLOW_AVAILABLE and mlflow_manager):
        raise HTTPException(status_code=503, detail="MLflow integration not available")

    results = mlflow_manager.load_registered_models()
    return {"loaded": results}


@app.get("/models/{model_type}/versions")
async def list_model_versions(
    model_type: str,
    limit: int = 20,
    _: Dict[str, Any] = Depends(
        require_roles({"system_admin", "data_engineer", "field_operator"})
    ),
):
    """List model versions from MLflow registry."""
    if not (MLFLOW_AVAILABLE and mlflow_manager):
        raise HTTPException(status_code=503, detail="MLflow integration not available")
    registry_name = MODEL_TYPE_TO_REGISTRY.get(model_type)
    if not registry_name:
        raise HTTPException(status_code=400, detail=f"Unknown model type: {model_type}")
    try:
        versions = mlflow_manager.list_model_versions(registry_name, limit=limit)
        return {
            "model_type": model_type,
            "registry": registry_name,
            "versions": versions,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list versions: {exc}")


@app.post("/models/{model_type}/compare")
async def compare_model_versions(
    model_type: str,
    request: ModelCompareRequest,
    _: Dict[str, Any] = Depends(require_roles({"system_admin", "data_engineer"})),
):
    """Compare baseline/candidate model versions."""
    if not (MLFLOW_AVAILABLE and mlflow_manager):
        raise HTTPException(status_code=503, detail="MLflow integration not available")
    registry_name = MODEL_TYPE_TO_REGISTRY.get(model_type)
    if not registry_name:
        raise HTTPException(status_code=400, detail=f"Unknown model type: {model_type}")
    try:
        result = mlflow_manager.compare_model_versions(
            model_name=registry_name,
            baseline_version=request.baseline_version,
            candidate_version=request.candidate_version,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Comparison failed: {exc}")


@app.post("/models/{model_type}/ab-test")
async def configure_ab_test(
    model_type: str,
    request: ABTestConfigRequest,
    _: Dict[str, Any] = Depends(require_roles({"system_admin", "data_engineer"})),
):
    """Configure A/B test rollout for inference routing."""
    if not (MLFLOW_AVAILABLE and mlflow_manager):
        raise HTTPException(status_code=503, detail="MLflow integration not available")
    if model_type == "time_series_forecast":
        raise HTTPException(
            status_code=400,
            detail="A/B testing currently supports only inference endpoints.",
        )
    if model_type not in MODEL_TYPE_TO_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown model type: {model_type}")

    try:
        cfg = mlflow_manager.configure_ab_test(
            model_key=model_type,
            baseline_version=request.baseline_version,
            candidate_version=request.candidate_version,
            candidate_weight=request.candidate_weight,
            seed=request.seed,
        )
        return {"model_type": model_type, "ab_test": cfg}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"A/B configuration failed: {exc}")


@app.get("/models/{model_type}/ab-test")
async def get_ab_test_config(
    model_type: str,
    _: Dict[str, Any] = Depends(
        require_roles({"system_admin", "data_engineer", "field_operator"})
    ),
):
    """Get active A/B test configuration."""
    if not (MLFLOW_AVAILABLE and mlflow_manager):
        raise HTTPException(status_code=503, detail="MLflow integration not available")
    cfg = mlflow_manager.get_ab_test(model_type)
    if not cfg:
        return {"model_type": model_type, "ab_test": None}
    return {"model_type": model_type, "ab_test": cfg}


@app.post("/models/{model_type}/drift/baseline")
async def set_drift_baseline(
    model_type: str,
    request: DriftBaselineRequest,
    _: Dict[str, Any] = Depends(require_roles({"system_admin", "data_engineer"})),
):
    """Set feature distribution baseline for drift detection."""
    if not (MLFLOW_AVAILABLE and mlflow_manager):
        raise HTTPException(status_code=503, detail="MLflow integration not available")
    if model_type not in MODEL_TYPE_TO_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown model type: {model_type}")
    try:
        baseline = mlflow_manager.set_feature_baseline(model_type, request.features)
        return {"model_type": model_type, "baseline": baseline}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Baseline creation failed: {exc}")


@app.post("/models/{model_type}/drift/detect")
async def detect_drift(
    model_type: str,
    request: DriftDetectRequest,
    _: Dict[str, Any] = Depends(
        require_roles({"system_admin", "data_engineer", "field_operator"})
    ),
):
    """Detect feature drift against the configured baseline."""
    if not (MLFLOW_AVAILABLE and mlflow_manager):
        raise HTTPException(status_code=503, detail="MLflow integration not available")
    if model_type not in MODEL_TYPE_TO_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown model type: {model_type}")
    try:
        result = mlflow_manager.detect_feature_drift(
            model_key=model_type,
            features=request.features,
            threshold=request.threshold,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Drift detection failed: {exc}")


@app.post("/federated/nodes/{node_id}/update")
async def submit_federated_update(
    node_id: str,
    request: FederatedNodeUpdateRequest,
    _: Dict[str, Any] = Depends(
        require_roles({"system_admin", "data_engineer", "field_operator"})
    ),
):
    """Register an edge node's local model update (weights only, never raw data)."""
    try:
        node = federated_coordinator.submit_local_update(
            node_id=node_id,
            well_name=request.well_name,
            location=request.location,
            local_weights=request.local_weights,
            local_accuracy=request.local_accuracy,
            data_size=request.data_size,
        )
        return {
            "node_id": node.node_id,
            "well_name": node.well_name,
            "location": node.location,
            "local_accuracy": node.local_accuracy,
            "data_size": node.data_size,
            "status": node.status,
            "last_sync": node.last_sync,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/federated/nodes/{node_id}/train-and-submit")
async def train_and_submit_federated_update(
    node_id: str,
    request: FederatedLocalTrainRequest,
    _: Dict[str, Any] = Depends(
        require_roles({"system_admin", "data_engineer", "field_operator"})
    ),
):
    """Fit a local model on this node's own samples and submit only the
    resulting weights -- the samples/labels in the request body are what an
    edge node would otherwise keep entirely local; this endpoint exists so
    the training step can be exercised/demonstrated centrally too."""
    try:
        trained = train_local_linear_model(request.samples, request.labels)
        node = federated_coordinator.submit_local_update(
            node_id=node_id,
            well_name=request.well_name,
            location=request.location,
            local_weights=trained["local_weights"],
            local_accuracy=trained["local_accuracy"],
            data_size=trained["data_size"],
        )
        return {
            "node_id": node.node_id,
            "local_accuracy": node.local_accuracy,
            "data_size": node.data_size,
            "status": node.status,
            "last_sync": node.last_sync,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/federated/aggregate")
async def aggregate_federated_round(
    request: FederatedAggregateRequest,
    _: Dict[str, Any] = Depends(require_roles({"system_admin"})),
):
    """Run one FedAvg aggregation round over all currently-registered nodes."""
    try:
        return federated_coordinator.aggregate_round(min_nodes=request.min_nodes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/federated/nodes")
async def list_federated_nodes(
    _: Dict[str, Any] = Depends(
        require_roles({"system_admin", "data_engineer", "field_operator"})
    ),
):
    return {"nodes": federated_coordinator.get_state()["nodes"]}


@app.get("/federated/global-model")
async def get_federated_global_model(
    _: Dict[str, Any] = Depends(
        require_roles({"system_admin", "data_engineer", "field_operator"})
    ),
):
    state = federated_coordinator.get_state()
    return {
        "global_model": state["global_model"],
        "round_history": state["round_history"],
    }


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
