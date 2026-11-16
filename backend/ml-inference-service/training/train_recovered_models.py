from pathlib import Path
import json
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, IsolationForest
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, accuracy_score, f1_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

ROOT = Path("/tmp/dof-recovery")
OUT = Path(__file__).resolve().parents[1] / "models"
OUT.mkdir(parents=True, exist_ok=True)
metrics = {}

def save(name, model, info):
    joblib.dump(model, OUT / f"{name}.joblib")
    metrics[name] = info
    print(f"[SAVED] {name}")

# 1. NASA C-MAPSS RUL
try:
    base = ROOT / "extracted/cmaps/CMaps"
    cols = ["unit", "cycle"] + [f"setting_{i}" for i in range(1, 4)] + [f"sensor_{i}" for i in range(1, 22)]
    train = pd.read_csv(base / "train_FD001.txt", sep=r"\s+", header=None).dropna(axis=1, how="all")
    train.columns = cols
    max_cycle = train.groupby("unit").cycle.max()
    train["RUL"] = train.apply(lambda r: max_cycle[r.unit] - r.cycle, axis=1).clip(upper=125)

    feature_cols = cols[1:]
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr, va = next(splitter.split(train[feature_cols], train.RUL, groups=train.unit))
    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("rf", RandomForestRegressor(n_estimators=160, min_samples_leaf=2, n_jobs=-1, random_state=42))
    ])
    model.fit(train.iloc[tr][feature_cols], train.iloc[tr].RUL)
    pred = model.predict(train.iloc[va][feature_cols])
    save("nasa_cmaps_fd001_rul", model, {
        "dataset": "NASA C-MAPSS FD001",
        "target": "RUL capped at 125 cycles",
        "features": feature_cols,
        "validation": "engine-group holdout",
        "mae": float(mean_absolute_error(train.iloc[va].RUL, pred)),
        "rmse": float(np.sqrt(mean_squared_error(train.iloc[va].RUL, pred))),
        "r2": float(r2_score(train.iloc[va].RUL, pred)),
        "validation_engines": int(train.iloc[va].unit.nunique())
    })
except Exception as e:
    metrics["nasa_cmaps_fd001_rul_error"] = str(e)
    print("[ERROR] NASA:", e)

# 2. CWRU bearing fault classification from engineered features
try:
    path = ROOT / "extracted/cwru/feature_time_48k_2048_load_1.csv"
    df = pd.read_csv(path)
    target = next((c for c in df.columns if c.lower() in
                   {"label", "class", "fault", "fault_type", "status", "type"}), None)
    if target is None:
        raise ValueError(f"No recognized target column. Columns: {list(df.columns)}")

    X = df.drop(columns=[target]).select_dtypes(include=[np.number])
    y = df[target].astype(str)
    if X.shape[1] == 0 or y.nunique() < 2:
        raise ValueError("Insufficient numeric features or classes")

    Xtr, Xva, ytr, yva = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("rf", RandomForestClassifier(n_estimators=180, class_weight="balanced",
                                      n_jobs=-1, random_state=42))
    ])
    model.fit(Xtr, ytr)
    pred = model.predict(Xva)
    save("cwru_bearing_classifier", model, {
        "dataset": "CWRU 48kHz load 1 engineered features",
        "target_column": target,
        "features": list(X.columns),
        "classes": list(map(str, model.classes_)),
        "validation": "stratified random holdout",
        "accuracy": float(accuracy_score(yva, pred)),
        "macro_f1": float(f1_score(yva, pred, average="macro"))
    })
except Exception as e:
    metrics["cwru_bearing_classifier_error"] = str(e)
    print("[ERROR] CWRU:", e)

# 3. Industrial sensor anomaly detection (unsupervised)
try:
    path = ROOT / "extracted/sensor/sensor.csv"
    df = pd.read_csv(path, low_memory=False)
    X = df.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan)
    X = X.dropna(axis=1, how="all")
    if X.empty:
        raise ValueError("No numeric sensor columns found")
    X = X.sample(min(len(X), 200000), random_state=42)
    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("iforest", IsolationForest(n_estimators=150, contamination="auto",
                                   n_jobs=-1, random_state=42))
    ])
    model.fit(X)
    scores = model.decision_function(X)
    save("industrial_sensor_anomaly", model, {
        "dataset": "Recovered industrial sensor time series",
        "features": list(X.columns),
        "method": "IsolationForest",
        "training_rows": int(len(X)),
        "anomaly_fraction_on_training_sample": float(np.mean(model.predict(X) == -1)),
        "score_mean": float(np.mean(scores))
    })
except Exception as e:
    metrics["industrial_sensor_anomaly_error"] = str(e)
    print("[ERROR] Sensor:", e)

(OUT / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
print("\n===== TRAINING SUMMARY =====")
print(json.dumps(metrics, indent=2))
print(f"\nArtifacts: {OUT}")
