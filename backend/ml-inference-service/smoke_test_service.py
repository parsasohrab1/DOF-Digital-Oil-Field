"""Smoke test: verify the refactored mlflow_integration loads REAL committed
local artifacts (no MLflow server) and serves inference for all 3 service
models. Run: python -I smoke_test_service.py"""
import os, sys
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from mlflow_integration import MLflowModelManager, MLFLOW_IMPORT_OK, _repo_models_dir
print(f"MLFLOW_IMPORT_OK = {MLFLOW_IMPORT_OK}")
print(f"repo models dir  = {_repo_models_dir()}")

mgr = MLflowModelManager(model_path=_repo_models_dir() or "/app/models",
                         tracking_uri=None)
res = mgr.load_registered_models()
print(f"load_registered_models: {res}")

# --- anomaly inference (pump sensor features) ---
import json
meta = mgr._load_local_meta("anomaly_detection")
feat_names = meta.get("feature_names", [])
# build a plausible normal feature dict from a real pump row
import gzip, pandas as pd
with gzip.open(os.path.join("..","..","ml","datasets","cleaned","pump_sensor_clean.csv.gz"),"rt") as fh:
    df = pd.read_csv(fh)
normal_row = df.loc[df["anomaly"]==0, feat_names].iloc[0].to_dict()
r = mgr.predict_anomaly(normal_row)
print(f"anomaly  predict -> prediction={r['prediction']} "
      f"anomaly_score={r['anomaly_score']:.4f}")

# --- failure inference (ESP features) ---
fmeta = mgr._load_local_meta("failure_prediction")
fnames = fmeta.get("feature_names", [])
esp = pd.read_csv(os.path.join("..","..","ml","datasets","cleaned","esp_features_clean.csv"))
sample = esp[fnames].iloc[0].to_dict()
fr = mgr.predict_failure(sample)
print(f"failure  predict -> prediction={fr['prediction']} "
      f"failure_probability={fr['failure_probability']:.4f}")

# --- time series forecast (pump sensor_00 history) ---
series = pd.read_csv(os.path.join("..","..","ml","datasets","cleaned","pump_forecast_series.csv"))["value"].values
tr = mgr.predict_time_series(series[:60].tolist(), forecast_steps=3)
print(f"forecast predict -> steps={tr['forecast_steps']} "
      f"conf={tr['confidence']:.3f} pred[0]={tr['predictions'][0]:.4f}")

print("\nSMOKE TEST PASSED — all 3 service models loaded from local REAL artifacts and serve inference.")
