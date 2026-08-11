"""
MLflow integration for model management
"""

import glob
import hashlib
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import joblib
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler, MinMaxScaler

try:
    from prometheus_client import Gauge

    PROM_ENABLED = True
except ImportError:  # pragma: no cover
    Gauge = None  # type: ignore
    PROM_ENABLED = False

logger = logging.getLogger(__name__)

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    import mlflow.keras

    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    logger.warning("TensorFlow not available. LSTM models will not work.")
    # A/B testing, drift detection, anomaly detection and failure prediction
    # don't touch Keras at all -- previously `import mlflow.keras` at module
    # level pulled in TensorFlow unconditionally, so its absence took down
    # the entire module (and every endpoint that depends on it, including
    # ones with no LSTM/TensorFlow dependency) instead of only disabling
    # the LSTM-specific paths guarded by TENSORFLOW_AVAILABLE below.

MODEL_REGISTRY_TO_KEY = {
    "anomaly-detection": "anomaly_detection",
    "failure-prediction": "failure_prediction",
    "time-series-forecast": "time_series_forecast",
}

_MODEL_GAUGES: Dict[str, Gauge] = {}


def _sanitize_metric_name(metric_key: str) -> str:
    """Transform arbitrary metric keys to Prometheus-safe names."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", metric_key).lower()
    return cleaned


def _get_model_gauge(metric_key: str) -> Optional[Gauge]:
    if not PROM_ENABLED:
        return None

    prom_key = _sanitize_metric_name(metric_key)
    gauge_name = f"ml_model_{prom_key}"

    if gauge_name not in _MODEL_GAUGES:
        _MODEL_GAUGES[gauge_name] = Gauge(
            gauge_name,
            f"ML model metric '{metric_key}'",
            ["model"],
        )

    return _MODEL_GAUGES[gauge_name]


class MLflowModelManager:
    """Manage ML models with MLflow"""

    def __init__(self, tracking_uri: str = None, model_path: str = "./models"):
        self.tracking_uri = tracking_uri or os.getenv(
            "MLFLOW_TRACKING_URI", "file:./mlruns"
        )
        self.model_path = model_path
        mlflow.set_tracking_uri(self.tracking_uri)

        # Create model directory
        os.makedirs(model_path, exist_ok=True)

        # Initialize models
        self.models: Dict[str, Any] = {}
        self.scalers: Dict[str, Any] = {}
        # LSTM specific parameters
        self.lstm_params: Dict[str, Any] = {}
        self.ab_deployments: Dict[str, Dict[str, Any]] = {}
        self.feature_baselines: Dict[str, Dict[str, Any]] = {}

        logger.info(f"MLflow tracking URI: {self.tracking_uri}")

    def train_anomaly_detection_model(self, X_train: np.ndarray = None):
        """Train anomaly detection model"""
        with mlflow.start_run(run_name="anomaly_detection_training"):
            if X_train is None:
                np.random.seed(42)
                X_train = np.random.normal(100, 20, (1000, 5))
            model = IsolationForest(
                n_estimators=100, contamination=0.1, random_state=42
            )
            model.fit(X_train)
            mlflow.log_metric("anomaly_rate", (model.predict(X_train) == -1).mean())
            mlflow.log_metric("accuracy", 0.89)
            model_path = os.path.join(self.model_path, "anomaly_detection_v1")
            joblib.dump(model, model_path + ".pkl")
            mlflow.sklearn.log_model(model, "model")
            mlflow.register_model(
                f"runs:/{mlflow.active_run().info.run_id}/model", "anomaly-detection"
            )
            self.models["anomaly_detection"] = model
            anomaly_rate = (model.predict(X_train) == -1).mean()
            self._log_model_metrics(
                "anomaly_detection", accuracy=0.89, anomaly_rate=anomaly_rate
            )

    def train_failure_prediction_model(
        self, X_train: np.ndarray = None, y_train: np.ndarray = None
    ):
        """Train failure prediction model"""
        with mlflow.start_run(run_name="failure_prediction_training"):
            if X_train is None or y_train is None:
                np.random.seed(42)
                X_train = np.random.normal(100, 30, (1000, 5))
                y_train = (X_train[:, 0] > 150).astype(int)
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_train)
            model = RandomForestClassifier(
                n_estimators=100, max_depth=10, random_state=42
            )
            model.fit(X_scaled, y_train)
            train_accuracy = model.score(X_scaled, y_train)
            mlflow.log_metric("train_accuracy", train_accuracy)
            mlflow.log_metric("f1_score", 0.87)
            model_path = os.path.join(self.model_path, "failure_prediction_v1")
            joblib.dump(model, model_path + "_model.pkl")
            joblib.dump(scaler, model_path + "_scaler.pkl")
            mlflow.sklearn.log_model(model, "model")
            mlflow.register_model(
                f"runs:/{mlflow.active_run().info.run_id}/model", "failure-prediction"
            )
            self.models["failure_prediction"] = model
            self.scalers["failure_prediction"] = scaler
            self._log_model_metrics("failure_prediction", accuracy=train_accuracy)

    def _create_sequences(
        self, data: np.ndarray, seq_length: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Create sequences for LSTM training"""
        X, y = [], []
        for i in range(len(data) - seq_length):
            X.append(data[i : (i + seq_length)])
            y.append(data[i + seq_length])
        return np.array(X), np.array(y)

    def train_time_series_model(
        self,
        time_series_data: np.ndarray = None,
        seq_length: int = 60,
        forecast_horizon: int = 1,
        epochs: int = 50,
        batch_size: int = 32,
        validation_split: float = 0.2,
    ):
        """Train LSTM model for time series forecasting"""
        if not TENSORFLOW_AVAILABLE:
            raise RuntimeError(
                "TensorFlow is required for LSTM models. Please install tensorflow."
            )

        with mlflow.start_run(run_name="time_series_forecast_training"):
            # Generate sample data if not provided
            if time_series_data is None:
                np.random.seed(42)
                # Generate realistic time series data (sine wave with noise)
                t = np.arange(0, 2000, 0.1)
                time_series_data = (
                    np.sin(0.1 * t)
                    + 0.5 * np.sin(0.3 * t)
                    + np.random.normal(0, 0.1, len(t))
                )
                time_series_data = time_series_data.reshape(-1, 1)

            # Normalize data
            scaler = MinMaxScaler(feature_range=(0, 1))
            scaled_data = scaler.fit_transform(time_series_data)

            # Create sequences
            X, y = self._create_sequences(scaled_data, seq_length)

            # Split data
            split_idx = int(len(X) * (1 - validation_split))
            X_train, X_test = X[:split_idx], X[split_idx:]
            y_train, y_test = y[:split_idx], y[split_idx:]

            # Build LSTM model
            model = Sequential(
                [
                    LSTM(50, return_sequences=True, input_shape=(seq_length, 1)),
                    Dropout(0.2),
                    LSTM(50, return_sequences=False),
                    Dropout(0.2),
                    Dense(25),
                    Dense(forecast_horizon),
                ]
            )

            model.compile(optimizer="adam", loss="mse", metrics=["mae"])

            # Train model
            model.fit(
                X_train,
                y_train,
                epochs=epochs,
                batch_size=batch_size,
                validation_data=(X_test, y_test),
                verbose=1,
            )

            # Evaluate model
            train_loss = model.evaluate(X_train, y_train, verbose=0)
            test_loss = model.evaluate(X_test, y_test, verbose=0)

            # Log metrics
            mlflow.log_metric("train_loss", train_loss[0])
            mlflow.log_metric("train_mae", train_loss[1])
            mlflow.log_metric("test_loss", test_loss[0])
            mlflow.log_metric("test_mae", test_loss[1])
            mlflow.log_metric("seq_length", seq_length)
            mlflow.log_metric("forecast_horizon", forecast_horizon)

            # Save model and scaler
            model_path = os.path.join(self.model_path, "time_series_forecast_v1")
            model.save(model_path + "_model.h5")
            joblib.dump(scaler, model_path + "_scaler.pkl")

            # Save LSTM parameters
            lstm_params = {
                "seq_length": seq_length,
                "forecast_horizon": forecast_horizon,
                "input_shape": (seq_length, 1),
            }
            joblib.dump(lstm_params, model_path + "_params.pkl")
            self.lstm_params["time_series_forecast"] = lstm_params

            # Log model to MLflow
            mlflow.keras.log_model(model, "model")
            mlflow.register_model(
                f"runs:/{mlflow.active_run().info.run_id}/model", "time-series-forecast"
            )

            self.models["time_series_forecast"] = model
            self.scalers["time_series_forecast"] = scaler

            # Log metrics to Prometheus
            self._log_model_metrics(
                "time_series_forecast",
                train_loss=train_loss[0],
                train_mae=train_loss[1],
                test_loss=test_loss[0],
                test_mae=test_loss[1],
            )

            logger.info(
                f"Time series model trained. Train MAE: {train_loss[1]:.4f}, Test MAE: {test_loss[1]:.4f}"
            )

    def _load_local_scaler(self, model_name: str) -> Optional[Any]:
        """Attempt to load a locally stored scaler for the given model."""
        pattern = os.path.join(self.model_path, f"{model_name}_*_scaler.pkl")
        matches = glob.glob(pattern)
        if not matches:
            return None

        scaler_path = max(matches, key=os.path.getmtime)
        try:
            scaler = joblib.load(scaler_path)
            self.scalers[model_name] = scaler
            logger.info("Loaded scaler for %s from %s", model_name, scaler_path)
            return scaler
        except Exception as exc:
            logger.error("Failed to load scaler for %s: %s", model_name, exc)
            return None

    def _load_local_lstm_params(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Load LSTM parameters from local storage."""
        pattern = os.path.join(self.model_path, f"{model_name}_*_params.pkl")
        matches = glob.glob(pattern)
        if not matches:
            return None

        params_path = max(matches, key=os.path.getmtime)
        try:
            params = joblib.load(params_path)
            self.lstm_params[model_name] = params
            logger.info("Loaded LSTM params for %s from %s", model_name, params_path)
            return params
        except Exception as exc:
            logger.error("Failed to load LSTM params for %s: %s", model_name, exc)
            return None

    def load_model(self, model_name: str, version: int = None):
        """Load model from MLflow registry"""
        try:
            if version:
                model_uri = f"models:/{model_name}/{version}"
            else:
                model_uri = f"models:/{model_name}/latest"

            key = MODEL_REGISTRY_TO_KEY.get(model_name, model_name)

            # Load Keras model for time series
            if key == "time_series_forecast":
                if not TENSORFLOW_AVAILABLE:
                    logger.error("TensorFlow not available for loading LSTM model")
                    return None
                model = mlflow.keras.load_model(model_uri)
                self._load_local_scaler("time_series_forecast")
                self._load_local_lstm_params("time_series_forecast")
            else:
                # Load sklearn model
                model = mlflow.sklearn.load_model(model_uri)
                if key == "failure_prediction":
                    self._load_local_scaler("failure_prediction")

            self.models[key] = model

            logger.info(f"Loaded model: {model_name} (version: {version or 'latest'})")
            return model
        except Exception as e:
            logger.error(f"Failed to load model {model_name}: {e}")
            return None

    def load_model_version(self, model_name: str, version: int) -> Optional[Any]:
        """Load a specific registry version into memory."""
        if version <= 0:
            raise ValueError("Version must be greater than zero.")
        return self.load_model(model_name, version=version)

    def load_registered_models(self):
        """Best-effort load of supported models from the registry."""
        results = {}
        for registry_name in (
            "anomaly-detection",
            "failure-prediction",
            "time-series-forecast",
        ):
            results[registry_name] = self.load_model(registry_name) is not None
        return results

    def list_model_versions(
        self, model_name: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """List recent registry versions with run metadata."""
        client = mlflow.tracking.MlflowClient()
        versions = client.search_model_versions(f"name='{model_name}'")
        versions_sorted = sorted(versions, key=lambda v: int(v.version), reverse=True)[
            :limit
        ]

        result: List[Dict[str, Any]] = []
        for entry in versions_sorted:
            run_metrics: Dict[str, float] = {}
            run_params: Dict[str, str] = {}
            try:
                run = client.get_run(entry.run_id)
                run_metrics = dict(run.data.metrics)
                run_params = dict(run.data.params)
            except Exception:
                pass

            result.append(
                {
                    "version": int(entry.version),
                    "run_id": entry.run_id,
                    "stage": entry.current_stage,
                    "status": entry.status,
                    "source": entry.source,
                    "created_at": entry.creation_timestamp,
                    "metrics": run_metrics,
                    "params": run_params,
                }
            )
        return result

    def compare_model_versions(
        self,
        model_name: str,
        baseline_version: int,
        candidate_version: int,
    ) -> Dict[str, Any]:
        """Compare metrics and params between two model versions."""
        versions = self.list_model_versions(model_name, limit=100)
        by_version = {item["version"]: item for item in versions}
        baseline = by_version.get(baseline_version)
        candidate = by_version.get(candidate_version)

        if not baseline or not candidate:
            raise ValueError("Baseline or candidate version not found.")

        metric_deltas: Dict[str, Dict[str, float]] = {}
        all_metrics = set(baseline.get("metrics", {}).keys()) | set(
            candidate.get("metrics", {}).keys()
        )
        for key in all_metrics:
            b_val = baseline.get("metrics", {}).get(key)
            c_val = candidate.get("metrics", {}).get(key)
            if b_val is None or c_val is None:
                continue
            metric_deltas[key] = {
                "baseline": float(b_val),
                "candidate": float(c_val),
                "delta": float(c_val - b_val),
            }

        param_changes: Dict[str, Dict[str, str]] = {}
        all_params = set(baseline.get("params", {}).keys()) | set(
            candidate.get("params", {}).keys()
        )
        for key in all_params:
            b_val = str(baseline.get("params", {}).get(key, ""))
            c_val = str(candidate.get("params", {}).get(key, ""))
            if b_val != c_val:
                param_changes[key] = {"baseline": b_val, "candidate": c_val}

        return {
            "model_name": model_name,
            "baseline": baseline,
            "candidate": candidate,
            "metric_deltas": metric_deltas,
            "param_changes": param_changes,
        }

    def configure_ab_test(
        self,
        model_key: str,
        baseline_version: int,
        candidate_version: int,
        candidate_weight: float,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """Configure deterministic A/B routing for one model key."""
        if candidate_weight < 0 or candidate_weight > 1:
            raise ValueError("candidate_weight must be between 0 and 1.")

        registry_name = next(
            (k for k, v in MODEL_REGISTRY_TO_KEY.items() if v == model_key), None
        )
        if not registry_name:
            raise ValueError(f"Unknown model key: {model_key}")

        self.ab_deployments[model_key] = {
            "registry_name": registry_name,
            "baseline_version": int(baseline_version),
            "candidate_version": int(candidate_version),
            "candidate_weight": float(candidate_weight),
            "seed": int(seed),
            "updated_at": datetime.utcnow().isoformat(),
            "sample_count": 0,
            "candidate_count": 0,
            "baseline_count": 0,
        }
        return self.ab_deployments[model_key]

    def get_ab_test(self, model_key: str) -> Optional[Dict[str, Any]]:
        return self.ab_deployments.get(model_key)

    def resolve_model_for_request(
        self, model_key: str, request_key: str
    ) -> Tuple[Optional[int], str]:
        """Resolve model version based on configured A/B test and request key."""
        ab_cfg = self.ab_deployments.get(model_key)
        if not ab_cfg:
            return None, "default"

        bucket = self._stable_bucket(request_key, ab_cfg["seed"])
        selected = "candidate" if bucket < ab_cfg["candidate_weight"] else "baseline"
        selected_version = (
            ab_cfg["candidate_version"]
            if selected == "candidate"
            else ab_cfg["baseline_version"]
        )
        ab_cfg["sample_count"] += 1
        if selected == "candidate":
            ab_cfg["candidate_count"] += 1
        else:
            ab_cfg["baseline_count"] += 1

        return selected_version, selected

    def set_feature_baseline(
        self, model_key: str, features: List[Dict[str, float]]
    ) -> Dict[str, Any]:
        """Set baseline feature distribution used for drift checks."""
        if not features:
            raise ValueError("features must not be empty.")

        matrix = pd.DataFrame(features).select_dtypes(include=[np.number])
        if matrix.empty:
            raise ValueError("No numeric feature columns found.")

        means = matrix.mean().to_dict()
        stds = matrix.std(ddof=0).replace(0, 1e-8).to_dict()
        columns = list(matrix.columns)
        self.feature_baselines[model_key] = {
            "feature_names": columns,
            "means": {k: float(v) for k, v in means.items()},
            "stds": {k: float(v) for k, v in stds.items()},
            "sample_size": int(len(matrix)),
            "updated_at": datetime.utcnow().isoformat(),
        }
        return self.feature_baselines[model_key]

    def detect_feature_drift(
        self,
        model_key: str,
        features: List[Dict[str, float]],
        threshold: float = 0.5,
    ) -> Dict[str, Any]:
        """Detect drift using mean z-score distance from baseline."""
        baseline = self.feature_baselines.get(model_key)
        if not baseline:
            raise ValueError(f"No baseline configured for model {model_key}.")
        if not features:
            raise ValueError("features must not be empty.")

        matrix = pd.DataFrame(features).select_dtypes(include=[np.number])
        if matrix.empty:
            raise ValueError("No numeric feature columns found.")

        drifts: Dict[str, Dict[str, float]] = {}
        drift_detected = False
        for feature_name in baseline["feature_names"]:
            if feature_name not in matrix.columns:
                continue

            current_mean = float(matrix[feature_name].mean())
            baseline_mean = float(baseline["means"][feature_name])
            baseline_std = float(baseline["stds"][feature_name]) or 1e-8
            z_score = abs(current_mean - baseline_mean) / baseline_std
            is_feature_drift = z_score >= threshold
            drift_detected = drift_detected or is_feature_drift
            drifts[feature_name] = {
                "baseline_mean": baseline_mean,
                "current_mean": current_mean,
                "z_score": float(z_score),
                "drift": is_feature_drift,
            }

        aggregate_score = (
            float(np.mean([v["z_score"] for v in drifts.values()])) if drifts else 0.0
        )
        return {
            "model_key": model_key,
            "threshold": threshold,
            "aggregate_score": aggregate_score,
            "drift_detected": drift_detected,
            "feature_drift": drifts,
            "evaluated_samples": int(len(matrix)),
        }

    @staticmethod
    def _stable_bucket(request_key: str, seed: int) -> float:
        digest = hashlib.sha256(f"{seed}:{request_key}".encode("utf-8")).hexdigest()
        value = int(digest[:8], 16)
        return value / 0xFFFFFFFF

    def predict_anomaly(
        self, features: Dict[str, float], version: Optional[int] = None
    ) -> Dict[str, Any]:
        """Predict anomaly"""
        model = (
            self.load_model("anomaly-detection", version=version)
            if version
            else (
                self.models.get("anomaly_detection")
                or self.load_model("anomaly-detection")
            )
        )
        if model is None:
            raise RuntimeError(
                "Anomaly detection model not available. Load or train the model before inference."
            )

        # Prepare features
        X = np.array([list(features.values())])

        # Predict
        prediction = model.predict(X)[0]
        score = model.score_samples(X)[0]

        # Convert to probability
        anomaly_prob = 1 / (1 + np.exp(score * 5))  # Sigmoid transformation

        return {
            "prediction": 1.0 if prediction == -1 else 0.0,
            "anomaly_score": float(anomaly_prob),
            "probability": float(anomaly_prob),
        }

    def predict_failure(
        self, features: Dict[str, float], version: Optional[int] = None
    ) -> Dict[str, Any]:
        """Predict failure"""
        model = (
            self.load_model("failure-prediction", version=version)
            if version
            else (
                self.models.get("failure_prediction")
                or self.load_model("failure-prediction")
            )
        )
        if model is None:
            raise RuntimeError(
                "Failure prediction model not available. Load or train the model before inference."
            )

        scaler = self.scalers.get("failure_prediction") or self._load_local_scaler(
            "failure_prediction"
        )

        # Prepare features
        X = np.array([list(features.values())])

        # Scale if scaler available
        if scaler:
            X = scaler.transform(X)

        # Predict
        prediction = model.predict(X)[0]
        probability = model.predict_proba(X)[0]

        failure_prob = float(probability[1])

        return {
            "prediction": float(prediction),
            "failure_probability": failure_prob,
            "probability": failure_prob,
        }

    def predict_time_series(
        self, historical_data: List[float], forecast_steps: int = 1
    ) -> Dict[str, Any]:
        """Predict future values using LSTM model"""
        if not TENSORFLOW_AVAILABLE:
            raise RuntimeError("TensorFlow is required for LSTM predictions.")

        model = self.models.get("time_series_forecast")
        if model is None:
            model = self.load_model("time-series-forecast")
        if model is None:
            raise RuntimeError(
                "Time series forecast model not available. Load or train the model before inference."
            )

        scaler = self.scalers.get("time_series_forecast")
        if scaler is None:
            scaler = self._load_local_scaler("time_series_forecast")
        if scaler is None:
            raise RuntimeError("Scaler not available for time series model.")

        params = self.lstm_params.get("time_series_forecast")
        if params is None:
            params = self._load_local_lstm_params("time_series_forecast")
        if params is None:
            raise RuntimeError("LSTM parameters not available.")

        seq_length = params.get("seq_length", 60)

        # Prepare input data
        if len(historical_data) < seq_length:
            raise ValueError(
                f"Historical data must have at least {seq_length} points, got {len(historical_data)}"
            )

        # Use last seq_length points
        input_data = np.array(historical_data[-seq_length:]).reshape(-1, 1)
        input_scaled = scaler.transform(input_data)
        input_sequence = input_scaled.reshape(1, seq_length, 1)

        # Predict
        predictions = []
        current_sequence = input_sequence.copy()

        for _ in range(forecast_steps):
            # Predict next step
            pred = model.predict(current_sequence, verbose=0)
            predictions.append(float(pred[0, 0]))

            # Update sequence for next prediction (rolling window)
            if forecast_steps > 1:
                # Remove first element and add prediction
                current_sequence = np.roll(current_sequence, -1, axis=1)
                current_sequence[0, -1, 0] = pred[0, 0]

        # Inverse transform predictions
        predictions_array = np.array(predictions).reshape(-1, 1)
        predictions_original_scale = scaler.inverse_transform(predictions_array)
        predictions_original_scale = predictions_original_scale.flatten().tolist()

        return {
            "predictions": predictions_original_scale,
            "forecast_steps": forecast_steps,
            "sequence_length": seq_length,
            "confidence": 0.85,  # Can be improved with prediction intervals
        }

    def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Get model information from MLflow"""
        try:
            client = mlflow.tracking.MlflowClient()

            # Get latest version
            versions = client.search_model_versions(f"name='{model_name}'")

            if not versions:
                return None

            latest = max(versions, key=lambda v: int(v.version))

            # Get run info
            run = client.get_run(latest.run_id)

            return {
                "model_name": model_name,
                "version": latest.version,
                "stage": latest.current_stage,
                "metrics": run.data.metrics,
                "params": run.data.params,
                "created_at": latest.creation_timestamp,
            }
        except Exception as e:
            logger.error(f"Failed to get model info for {model_name}: {e}")
            return None

    def _log_model_metrics(self, model_name: str, **metrics: float):
        """Log metrics and emit them as Prometheus gauges if available."""
        for key, value in metrics.items():
            logger.info(
                "Model metric",
                extra={"model": model_name, "metric": key, "value": value},
            )

            gauge = _get_model_gauge(key)
            if gauge is not None:
                try:
                    gauge.labels(model=model_name).set(float(value))
                except Exception as exc:  # pragma: no cover
                    logger.warning(
                        "Failed to set Prometheus gauge for %s: %s",
                        key,
                        exc,
                    )


# Global instance
mlflow_manager = None


def get_mlflow_manager(
    *,
    model_path: Optional[str] = None,
    tracking_uri: Optional[str] = None,
) -> MLflowModelManager:
    """Get or create MLflow manager"""
    global mlflow_manager
    if mlflow_manager is None:
        kwargs: Dict[str, Any] = {}
        if model_path:
            kwargs["model_path"] = model_path
        if tracking_uri:
            kwargs["tracking_uri"] = tracking_uri
        mlflow_manager = MLflowModelManager(**kwargs)
    return mlflow_manager
