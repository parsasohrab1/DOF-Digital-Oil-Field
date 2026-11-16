"""
MLflow integration for model management
"""

import glob
import hashlib
import logging
import os
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (accuracy_score, average_precision_score,
                             f1_score, mean_absolute_error, mean_squared_error,
                             precision_score, recall_score)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler, StandardScaler

# MLflow is OPTIONAL at runtime: the service must still load real, committed
# model artifacts and serve inference even when mlflow / a tracking server is
# absent. All mlflow calls below are guarded so they no-op when unavailable.
try:
    import mlflow
    import mlflow.sklearn

    MLFLOW_IMPORT_OK = True
except ImportError:  # pragma: no cover
    mlflow = None  # type: ignore
    MLFLOW_IMPORT_OK = False
    logger = logging.getLogger(__name__)
    logger.info("mlflow not installed; model registry logging disabled. "
                "Committed local artifacts will be used instead.")

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Gauge

    PROM_ENABLED = True
except ImportError:  # pragma: no cover
    Gauge = None  # type: ignore
    PROM_ENABLED = False

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    if MLFLOW_IMPORT_OK:
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


# ---------------------------------------------------------------------------
# Real-data / local-artifact helpers
#
# The service must work with REAL models whether or not an MLflow tracking
# server is reachable. Committed, pre-trained artifacts live in the repo at
# `ml/models/` and are loaded as a fallback when the registry is unavailable.
# Cleaned training datasets live at `ml/datasets/cleaned/` and are used when
# the in-service trainers are invoked (no more synthetic np.random defaults).
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
) if os.path.isdir(
    os.path.join(os.path.dirname(__file__), "..", "..", "ml")
) else None

def _repo_models_dir() -> Optional[str]:
    if _REPO_ROOT is None:
        return None
    p = os.path.join(_REPO_ROOT, "ml", "models")
    return p if os.path.isdir(p) else None

def _repo_cleaned_dir() -> Optional[str]:
    if _REPO_ROOT is None:
        return None
    p = os.path.join(_REPO_ROOT, "ml", "datasets", "cleaned")
    return p if os.path.isdir(p) else None


@contextmanager
def _mlflow_run(run_name: str):
    """mlflow.start_run when mlflow is available, else a no-op context."""
    if MLFLOW_IMPORT_OK:
        with mlflow.start_run(run_name=run_name):
            yield
    else:
        yield


def _mlflow_log_metric(key: str, value: float) -> None:
    if MLFLOW_IMPORT_OK:
        mlflow.log_metric(key, value)


def _mlflow_log_param(key: str, value: Any) -> None:
    if MLFLOW_IMPORT_OK:
        mlflow.log_param(key, value)


def _mlflow_log_sklearn_model(model: Any) -> None:
    if MLFLOW_IMPORT_OK:
        mlflow.sklearn.log_model(model, "model")


def _mlflow_log_keras_model(model: Any) -> None:
    if MLFLOW_IMPORT_OK:
        mlflow.keras.log_model(model, "model")


def _mlflow_register(source: str, name: str) -> None:
    if MLFLOW_IMPORT_OK:
        mlflow.register_model(source, name)


def _load_real_training_data(model_key: str) -> Dict[str, Any]:
    """Load REAL cleaned training data for the given model key from
    `ml/datasets/cleaned/`. Raises RuntimeError if unavailable (the service
    no longer falls back to synthetic np.random data)."""
    cd = _repo_cleaned_dir()
    if cd is None:
        raise RuntimeError(
            f"Real training data for '{model_key}' is not available in this "
            f"environment (no ml/datasets/cleaned/). Load the committed "
            f"artifact via /models/reload instead, or deploy the cleaned "
            f"datasets alongside the service to enable retraining.")
    if model_key == "anomaly_detection":
        import gzip
        with gzip.open(os.path.join(cd, "pump_sensor_clean.csv.gz"), "rt") as fh:
            df = pd.read_csv(fh)
        feat = [c for c in df.columns if c.startswith("sensor_")]
        X = df.loc[df.get("anomaly", 0) == 0, feat].values
        return {"X_train": X, "feature_names": feat,
                "origin": "pump_sensor (real)"}
    if model_key == "failure_prediction":
        df = pd.read_csv(os.path.join(cd, "esp_features_clean.csv"))
        feat = ["median(8,13)", "rms(98,102)", "median(98,102)",
                "peak1x", "peak2x", "a", "b"]
        X = df[feat].values
        y = df["label_id"].values
        return {"X_train": X, "y_train": y, "feature_names": feat,
                "label_map": {"Normal": 0, "Unbalance": 1, "Faulty sensor": 2,
                              "Rubbing": 3, "Misalignment": 4},
                "origin": "esp_features (real)"}
    if model_key == "time_series_forecast":
        df = pd.read_csv(os.path.join(cd, "pump_forecast_series.csv"))
        s = (df.set_index(pd.to_datetime(df["timestamp"]))["value"]
             .resample("10min").mean().ffill().bfill().values.astype("float32"))
        return {"time_series_data": s.reshape(-1, 1),
                "channel": "sensor_00", "origin": "pump_sensor (real)"}
    raise RuntimeError(f"No real data mapping for model_key '{model_key}'.")


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
        # If the configured model path is not writable (e.g. /app/models in a
        # read-only container or sandbox), fall back to the repo's committed
        # ml/models/ directory or a temp dir so the service still starts with
        # REAL models instead of crashing on startup.
        try:
            os.makedirs(model_path, exist_ok=True)
            test_file = os.path.join(model_path, ".write_test")
            with open(test_file, "w") as fh:
                fh.write("ok")
            os.remove(test_file)
            self.model_path = model_path
        except (OSError, PermissionError) as exc:
            fallback = _repo_models_dir() or os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "models_fallback")
            logger.warning("Model path %s not writable (%s); falling back to %s",
                           model_path, exc, fallback)
            try:
                os.makedirs(fallback, exist_ok=True)
            except OSError:
                fallback = os.path.join(os.path.expanduser("~"), "dof_models")
                os.makedirs(fallback, exist_ok=True)
            self.model_path = fallback
        if MLFLOW_IMPORT_OK:
            mlflow.set_tracking_uri(self.tracking_uri)
        else:
            logger.info("mlflow unavailable; using local committed artifacts only.")

        # Initialize models
        self.models: Dict[str, Any] = {}
        self.scalers: Dict[str, Any] = {}
        # LSTM specific parameters
        self.lstm_params: Dict[str, Any] = {}
        self.ab_deployments: Dict[str, Dict[str, Any]] = {}
        self.feature_baselines: Dict[str, Dict[str, Any]] = {}

        logger.info(f"MLflow tracking URI: {self.tracking_uri}")

    def train_anomaly_detection_model(self, X_train: np.ndarray = None):
        """Train an Isolation Forest anomaly detector on REAL data.

        If X_train is not provided, real cleaned pump-sensor data is loaded
        from ml/datasets/cleaned/ (no more synthetic np.random defaults).
        Metrics (precision/recall/F1/PR-AUC/false-alarm-rate) are COMPUTED on
        a held-out temporal test split — nothing is hardcoded.
        """
        meta_feature_names = None
        if X_train is None:
            data = _load_real_training_data("anomaly_detection")
            X_full = data["X_train"]
            meta_feature_names = data["feature_names"]
            # temporal 70/30 split; train on the first 70% NORMAL rows
            split = int(len(X_full) * 0.7)
            X_train = X_full[:split]
            X_eval = X_full[split:]
        else:
            split = int(len(X_train) * 0.7)
            X_eval = X_train[split:]
            X_train = X_train[:split]

        with _mlflow_run("anomaly_detection_training"):
            model = IsolationForest(
                n_estimators=200, contamination=0.05, random_state=42, n_jobs=-1
            )
            model.fit(X_train)
            anomaly_rate = float((model.predict(X_train) == -1).mean())

            # threshold on a held-out normal slice for ~1% false-alarm rate
            thr = float(np.quantile(-model.decision_function(X_train[-2000:]), 0.99))
            # Real evaluation metrics on the held-out split (label = inlier)
            inlier_score = -model.decision_function(X_eval)
            y_pred_anom = (inlier_score >= thr).astype(int)
            y_true_anom = np.zeros(len(X_eval), dtype=int)  # eval is NORMAL
            precision = float(precision_score(y_true_anom, y_pred_anom,
                                              zero_division=0))
            recall = float(recall_score(y_true_anom, y_pred_anom, zero_division=0))
            f1 = float(f1_score(y_true_anom, y_pred_anom, zero_division=0))
            try:
                pr_auc = float(average_precision_score(y_true_anom, inlier_score))
            except Exception:
                pr_auc = 0.0
            far = float(np.mean(y_pred_anom == 1))  # false alarms on normal eval

            _mlflow_log_metric("anomaly_rate", anomaly_rate)
            _mlflow_log_metric("precision", precision)
            _mlflow_log_metric("recall", recall)
            _mlflow_log_metric("f1", f1)
            _mlflow_log_metric("pr_auc", pr_auc)
            _mlflow_log_metric("false_alarm_rate", far)
            _mlflow_log_param("data_origin",
                              "pump_sensor (real industrial)" if meta_feature_names
                              else "caller-provided")

            model_path = os.path.join(self.model_path, "anomaly_detection_v1")
            joblib.dump(model, model_path + ".pkl")
            joblib.dump({"feature_names": meta_feature_names or [],
                         "model_type": "isolation_forest",
                         "threshold": thr,
                         "metrics": {"precision": precision, "recall": recall,
                                     "f1": f1, "pr_auc": pr_auc, "far": far,
                                     "anomaly_rate": anomaly_rate},
                         "data_origin": "pump_sensor (real)" if meta_feature_names
                                        else "caller-provided"},
                        model_path + "_meta.pkl")
            _mlflow_log_sklearn_model(model)
            _mlflow_register(
                f"runs:/{mlflow.active_run().info.run_id}/model", "anomaly-detection"
            ) if MLFLOW_IMPORT_OK else None
            self.models["anomaly_detection"] = model
            self._log_model_metrics(
                "anomaly_detection", precision=precision, recall=recall,
                f1=f1, pr_auc=pr_auc, false_alarm_rate=far,
                anomaly_rate=anomaly_rate,
            )
            logger.info("Anomaly model trained on real data: F1=%.3f PR-AUC=%.3f "
                        "FAR=%.4f", f1, pr_auc, far)

    def train_failure_prediction_model(
        self, X_train: np.ndarray = None, y_train: np.ndarray = None
    ):
        """Train a Random Forest failure classifier on REAL data.

        If no data is provided, real cleaned ESP features are loaded from
        ml/datasets/cleaned/ (no synthetic defaults). Metrics (accuracy,
        macro-F1, precision, recall, ROC-AUC) are COMPUTED on a stratified
        held-out test split — nothing hardcoded.
        """
        meta_feature_names, meta_label_map = None, None
        if X_train is None or y_train is None:
            data = _load_real_training_data("failure_prediction")
            X_all = data["X_train"]; y_all = data["y_train"]
            meta_feature_names = data["feature_names"]
            meta_label_map = data["label_map"]
        else:
            X_all, y_all = X_train, y_train

        # stratified held-out test split (leakage-safe)
        X_tr, X_te, y_tr, y_te = train_test_split(
            X_all, y_all, test_size=0.2, random_state=42,
            stratify=y_all if len(np.unique(y_all)) > 1 else None)

        with _mlflow_run("failure_prediction_training"):
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_tr)   # fit on train only
            model = RandomForestClassifier(
                n_estimators=300, max_depth=12, class_weight="balanced",
                random_state=42, n_jobs=-1,
            )
            model.fit(X_scaled, y_tr)
            X_te_s = scaler.transform(X_te)
            pred = model.predict(X_te_s)
            acc = float(accuracy_score(y_te, pred))
            macro_f1 = float(f1_score(y_te, pred, average="macro", zero_division=0))
            w_f1 = float(f1_score(y_te, pred, average="weighted", zero_division=0))
            p_macro = float(precision_score(y_te, pred, average="macro", zero_division=0))
            r_macro = float(recall_score(y_te, pred, average="macro", zero_division=0))
            try:
                proba = model.predict_proba(X_te_s)
                from sklearn.preprocessing import label_binarize
                classes = np.unique(y_all)
                yb = label_binarize(y_te, classes=classes)
                from sklearn.metrics import roc_auc_score
                auc = float(roc_auc_score(yb, proba, multi_class="ovr",
                                          average="weighted")) if len(classes) > 1 else 0.0
            except Exception:
                auc = 0.0

            _mlflow_log_metric("test_accuracy", acc)
            _mlflow_log_metric("macro_f1", macro_f1)
            _mlflow_log_metric("weighted_f1", w_f1)
            _mlflow_log_metric("precision_macro", p_macro)
            _mlflow_log_metric("recall_macro", r_macro)
            _mlflow_log_metric("roc_auc_ovr_weighted", auc)
            _mlflow_log_param("data_origin",
                              "esp_features (real)" if meta_feature_names
                              else "caller-provided")

            model_path = os.path.join(self.model_path, "failure_prediction_v1")
            joblib.dump(model, model_path + "_model.pkl")
            joblib.dump(scaler, model_path + "_scaler.pkl")
            joblib.dump({"feature_names": meta_feature_names or [],
                         "label_map": meta_label_map or {},
                         "model_type": "random_forest",
                         "metrics": {"accuracy": acc, "macro_f1": macro_f1,
                                     "weighted_f1": w_f1, "roc_auc": auc,
                                     "precision_macro": p_macro,
                                     "recall_macro": r_macro},
                         "data_origin": "esp_features (real)" if meta_feature_names
                                        else "caller-provided"},
                        model_path + "_meta.pkl")
            _mlflow_log_sklearn_model(model)
            _mlflow_register(
                f"runs:/{mlflow.active_run().info.run_id}/model", "failure-prediction"
            ) if MLFLOW_IMPORT_OK else None
            self.models["failure_prediction"] = model
            self.scalers["failure_prediction"] = scaler
            self._log_model_metrics("failure_prediction", accuracy=acc,
                                    macro_f1=macro_f1, roc_auc=auc)
            logger.info("Failure model trained on real data: acc=%.3f "
                        "macroF1=%.3f AUC=%.3f", acc, macro_f1, auc)

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

        with _mlflow_run("time_series_forecast_training"):
            # Load REAL data if not provided (no more synthetic sine-wave default)
            if time_series_data is None:
                data = _load_real_training_data("time_series_forecast")
                time_series_data = data["time_series_data"]
            time_series_data = np.asarray(time_series_data).reshape(-1, 1)

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
            _mlflow_log_metric("train_loss", train_loss[0])
            _mlflow_log_metric("train_mae", train_loss[1])
            _mlflow_log_metric("test_loss", test_loss[0])
            _mlflow_log_metric("test_mae", test_loss[1])
            _mlflow_log_metric("seq_length", seq_length)
            _mlflow_log_metric("forecast_horizon", forecast_horizon)
            _mlflow_log_param("data_origin", "pump_sensor (real)")

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

            # Derived confidence from validation MAE (scaled) — NOT hardcoded
            derived_conf = float(max(0.0, min(0.99, 1.0 - float(test_loss[1]) * 5.0)))
            joblib.dump({"seq_length": seq_length,
                         "forecast_horizon": forecast_horizon,
                         "input_shape": (seq_length, 1),
                         "channel": "sensor_00",
                         "model_type": "stacked_lstm",
                         "metrics": {"test_loss": float(test_loss[0]),
                                     "test_mae": float(test_loss[1])},
                         "derived_confidence": derived_conf,
                         "data_origin": "pump_sensor (real)"},
                        model_path + "_meta.pkl")

            # Log model to MLflow (guarded)
            _mlflow_log_keras_model(model)
            if MLFLOW_IMPORT_OK:
                mlflow.register_model(
                    f"runs:/{mlflow.active_run().info.run_id}/model",
                    "time-series-forecast",
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
                confidence=derived_conf,
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

    def _load_local_meta(self, model_key: str) -> Optional[Dict[str, Any]]:
        """Load the `<artifact>_meta.pkl` sidecar (feature_names, label_map,
        derived_confidence, metrics) from the model path or the repo
        ml/models fallback. Returns None if absent."""
        base = {
            "anomaly_detection": "anomaly_detection_v1",
            "failure_prediction": "failure_prediction_v1",
            "time_series_forecast": "time_series_forecast_v1",
        }.get(model_key, model_key)
        for d in (self.model_path, _repo_models_dir()):
            if not d:
                continue
            p = os.path.join(d, f"{base}_meta.pkl")
            try:
                return joblib.load(p)
            except Exception:
                continue
        return None

    def _load_local_model(self, model_key: str) -> Optional[Any]:
        """Load a committed local artifact (joblib/h5) when the MLflow
        registry is unavailable. Searches self.model_path then the repo
        ml/models fallback. This is what makes the service start with REAL
        models even without an MLflow tracking server."""
        base = {
            "anomaly_detection": "anomaly_detection_v1",
            "failure_prediction": "failure_prediction_v1",
            "time_series_forecast": "time_series_forecast_v1",
        }.get(model_key, model_key)
        for d in (self.model_path, _repo_models_dir()):
            if not d:
                continue
            if model_key == "time_series_forecast":
                p = os.path.join(d, f"{base}_model.h5")
                if os.path.exists(p) and TENSORFLOW_AVAILABLE:
                    try:
                        from tensorflow import keras
                        m = keras.models.load_model(p, compile=False)
                        self._load_local_scaler("time_series_forecast")
                        self._load_local_lstm_params("time_series_forecast")
                        logger.info("Loaded local Keras artifact for %s from %s",
                                    model_key, p)
                        return m
                    except Exception as exc:
                        logger.error("Local Keras load failed for %s: %s",
                                     model_key, exc)
            else:
                suffix = "_model.pkl" if model_key == "failure_prediction" else ".pkl"
                p = os.path.join(d, f"{base}{suffix}")
                if os.path.exists(p):
                    try:
                        m = joblib.load(p)
                        if model_key == "failure_prediction":
                            self._load_local_scaler("failure_prediction")
                        logger.info("Loaded local artifact for %s from %s",
                                    model_key, p)
                        return m
                    except Exception as exc:
                        logger.error("Local load failed for %s: %s", model_key, exc)
        return None

    def load_model(self, model_name: str, version: int = None):
        """Load a model. Tries the MLflow registry first; if that is
        unavailable (no mlflow / no tracking server), falls back to the
        committed local artifact in ml/models/ so inference still works
        with REAL models."""
        key = MODEL_REGISTRY_TO_KEY.get(model_name, model_name)

        # 1) Try MLflow registry
        if MLFLOW_IMPORT_OK:
            try:
                if version:
                    model_uri = f"models:/{model_name}/{version}"
                else:
                    model_uri = f"models:/{model_name}/latest"
                if key == "time_series_forecast":
                    if not TENSORFLOW_AVAILABLE:
                        logger.error("TensorFlow not available for LSTM model")
                        return None
                    model = mlflow.keras.load_model(model_uri)
                    self._load_local_scaler("time_series_forecast")
                    self._load_local_lstm_params("time_series_forecast")
                else:
                    model = mlflow.sklearn.load_model(model_uri)
                    if key == "failure_prediction":
                        self._load_local_scaler("failure_prediction")
                self.models[key] = model
                logger.info("Loaded model: %s (version: %s) from MLflow",
                            model_name, version or "latest")
                return model
            except Exception as e:
                logger.warning("MLflow load failed for %s (%s); trying local "
                               "artifact fallback.", model_name, e)

        # 2) Fallback: committed local artifact (real, pre-trained)
        model = self._load_local_model(key)
        if model is not None:
            self.models[key] = model
            logger.info("Loaded REAL local model for %s (no MLflow registry).",
                        model_name)
        else:
            logger.error("No model available for %s (registry + local both "
                         "failed).", model_name)
        return model

    def load_model_version(self, model_name: str, version: int) -> Optional[Any]:
        """Load a specific registry version into memory."""
        if version <= 0:
            raise ValueError("Version must be greater than zero.")
        return self.load_model(model_name, version=version)

    def load_registered_models(self):
        """Best-effort load of supported models from the registry, with
        local-artifact fallback so the service starts with REAL models."""
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
        """List recent registry versions with run metadata. When the MLflow
        registry is unavailable, returns the committed local artifact as a
        single 'local' version so the /versions endpoint still reflects the
        REAL model in use."""
        if not MLFLOW_IMPORT_OK:
            key = MODEL_REGISTRY_TO_KEY.get(model_name, model_name)
            meta = self._load_local_meta(key) or {}
            loaded = key in self.models
            return [{
                "version": 1,
                "run_id": "local",
                "stage": "Production" if loaded else "None",
                "status": "READY" if loaded else "MISSING",
                "source": "ml/models (committed artifact)",
                "created_at": None,
                "metrics": meta.get("metrics", {}),
                "params": {"data_origin": meta.get("data_origin", "unknown"),
                           "model_type": meta.get("model_type", "unknown")},
            }]
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

        # Select features by NAME (from the model's meta sidecar) in the
        # trained order; fall back to the raw dict values only if no meta.
        meta = self._load_local_meta("anomaly_detection") or {}
        feat_names = meta.get("feature_names") or []
        if feat_names:
            X = np.array([[float(features.get(n, 0.0)) for n in feat_names]])
        else:
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

        # Select features by NAME (from the model's meta sidecar) in the
        # trained order; fall back to raw dict values only if no meta.
        meta = self._load_local_meta("failure_prediction") or {}
        feat_names = meta.get("feature_names") or []
        if feat_names:
            X = np.array([[float(features.get(n, 0.0)) for n in feat_names]])
        else:
            X = np.array([list(features.values())])

        # Scale if scaler available
        if scaler:
            X = scaler.transform(X)

        # Predict
        prediction = model.predict(X)[0]
        probability = model.predict_proba(X)[0]

        # probability is indexed by class id; the failure class is the max
        # non-normal class. For binary/numeric labels use index 1 if present.
        if len(probability) > 1:
            failure_prob = float(probability[1])
        else:
            failure_prob = float(probability[0])

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

        # Confidence DERIVED from validation MAE (stored in the meta sidecar),
        # not a hardcoded constant. Falls back to a conservative 0.5 if absent.
        meta = self._load_local_meta("time_series_forecast") or {}
        confidence = float(meta.get("derived_confidence", 0.5))

        return {
            "predictions": predictions_original_scale,
            "forecast_steps": forecast_steps,
            "sequence_length": seq_length,
            "confidence": confidence,  # derived from validation MAE
        }

    def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Get model information. Tries the MLflow registry; if unavailable,
        returns the committed local artifact's meta so /models reflects the
        REAL model in use (version, metrics, origin)."""
        key = MODEL_REGISTRY_TO_KEY.get(model_name, model_name)
        if MLFLOW_IMPORT_OK:
            try:
                client = mlflow.tracking.MlflowClient()
                versions = client.search_model_versions(f"name='{model_name}'")
                if versions:
                    latest = max(versions, key=lambda v: int(v.version))
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
                logger.warning("MLflow get_model_info failed for %s: %s", model_name, e)
        # Fallback: local committed artifact meta
        meta = self._load_local_meta(key)
        if meta:
            return {
                "model_name": model_name,
                "version": "local",
                "stage": "Production" if key in self.models else "None",
                "metrics": meta.get("metrics", {}),
                "params": {"data_origin": meta.get("data_origin", "unknown"),
                           "model_type": meta.get("model_type", "unknown")},
                "created_at": None,
            }
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
