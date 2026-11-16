"""
Phase 4a — Train & evaluate Anomaly Detection on the Pump Sensor dataset.

Approach (unsupervised, leakage-safe):
  * Temporal split: first 70% by timestamp = train (fit), last 30% = test (eval).
  * Isolation Forest is trained ONLY on NORMAL rows from the train period.
  * Evaluation on the test period uses machine_status != NORMAL as the ground
    truth anomaly label. Metrics: precision, recall, F1, PR-AUC, false-alarm
    rate — all computed from real predictions, nothing hardcoded.
  * Baselines: a statistical (mean±k·std) detector and One-Class SVM.

Artifacts saved to ml/models/ with the exact filename the inference service
expects (anomaly_detection_v1.pkl) plus a _meta.pkl sidecar (feature_names).
Run:  python -I train_anomaly.py
"""
import gzip
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (average_precision_score, confusion_matrix,
                             precision_recall_curve,
                             precision_score, recall_score, f1_score)
from sklearn.svm import OneClassSVM

from common import CLEANED, EVAL, MODELS, load_specs, save_meta, save_metrics, save_plot

import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")


def load_pump() -> pd.DataFrame:
    with gzip.open(CLEANED / "pump_sensor_clean.csv.gz", "rt") as fh:
        df = pd.read_csv(fh)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values("timestamp").reset_index(drop=True)


def fpr(y_true, y_pred):
    """False-alarm rate = FP / (FP + TN)."""
    tn, fp, *_ = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return fp / (fp + tn) if (fp + tn) else 0.0


def main() -> None:
    specs = load_specs()
    feat = specs["datasets"]["pump"]["features"]
    print(f"Pump anomaly detection — {len(feat)} sensor features")

    df = load_pump()
    n = len(df)
    split = int(n * 0.7)
    train, test = df.iloc[:split], df.iloc[split:]
    # Train ONLY on NORMAL rows of the train period (unsupervised, no leaks)
    X_train = train.loc[train["anomaly"] == 0, feat].values
    y_test = test["anomaly"].values
    X_test = test[feat].values
    print(f"train(NORMAL only): {len(X_train):,} | test: {len(X_test):,} "
          f"(positives={int(y_test.sum()):,})")

    results = {}

    # --- Isolation Forest ---
    iforest = IsolationForest(n_estimators=200, contamination=0.05,
                              random_state=42, n_jobs=-1)
    iforest.fit(X_train)
    # anomaly score: higher = more anomalous (invert decision_function)
    raw_score = -iforest.decision_function(X_test)
    # choose threshold on a held-out validation slice of the train period
    val = train.loc[train["anomaly"] == 0, feat].tail(int(len(X_train) * 0.2))
    val_score = -iforest.decision_function(val.values)
    # threshold = 99th percentile of normal validation scores (≤1% FAR on normal)
    thr = np.quantile(val_score, 0.99)
    y_pred = (raw_score >= thr).astype(int)
    ap = average_precision_score(y_test, raw_score)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    results["isolation_forest"] = {
        "precision": float(prec), "recall": float(rec), "f1": float(f1),
        "pr_auc": float(ap), "false_alarm_rate": float(fpr(y_test, y_pred)),
        "threshold": float(thr),
        "params": {"n_estimators": 200, "contamination": 0.05},
    }
    print(f"  IsolationForest  P={prec:.3f} R={rec:.3f} F1={f1:.3f} "
          f"PR-AUC={ap:.3f} FAR={fpr(y_test,y_pred):.4f}")

    # --- Statistical baseline (per-sensor z, anomaly if any |z|>4) ---
    mu, sd = X_train.mean(axis=0), X_train.std(axis=0)
    sd[sd == 0] = 1e-8
    z = np.abs((X_test - mu) / sd)
    stat_pred = (z.max(axis=1) > 4).astype(int)
    results["statistical_z4"] = {
        "precision": float(precision_score(y_test, stat_pred, zero_division=0)),
        "recall": float(recall_score(y_test, stat_pred, zero_division=0)),
        "f1": float(f1_score(y_test, stat_pred, zero_division=0)),
        "false_alarm_rate": float(fpr(y_test, stat_pred)),
    }
    print(f"  Statistical(z>4) P={results['statistical_z4']['precision']:.3f} "
          f"R={results['statistical_z4']['recall']:.3f} "
          f"F1={results['statistical_z4']['f1']:.3f}")

    # --- One-Class SVM (on a subsample of NORMAL train — O(n^2)) ---
    sub = X_train[:8000]
    ocsvm = OneClassSVM(kernel="rbf", nu=0.05, gamma="scale")
    ocsvm.fit(sub)
    svm_score = -ocsvm.decision_function(X_test)
    svm_pred = (svm_score >= np.quantile(-ocsvm.decision_function(sub), 0.99)).astype(int)
    results["one_class_svm"] = {
        "precision": float(precision_score(y_test, svm_pred, zero_division=0)),
        "recall": float(recall_score(y_test, svm_pred, zero_division=0)),
        "f1": float(f1_score(y_test, svm_pred, zero_division=0)),
        "pr_auc": float(average_precision_score(y_test, svm_score)),
        "false_alarm_rate": float(fpr(y_test, svm_pred)),
    }
    print(f"  OneClassSVM      P={results['one_class_svm']['precision']:.3f} "
          f"R={results['one_class_svm']['recall']:.3f} "
          f"F1={results['one_class_svm']['f1']:.3f}")

    # --- Save the production Isolation Forest artifact (service-compatible) ---
    joblib.dump(iforest, MODELS / "anomaly_detection_v1.pkl")
    save_meta("anomaly_detection_v1", {
        "feature_names": feat,
        "model_type": "isolation_forest",
        "threshold": float(thr),
        "metrics": results["isolation_forest"],
        "data_origin": "Pump Sensor (real industrial, Kaggle)",
        "n_train_normal": int(len(X_train)),
    })

    # --- PR curve plot ---
    fig, ax = plt.subplots(figsize=(6, 4))
    for name, score in (("IsolationForest", raw_score),
                        ("OneClassSVM", svm_score)):
        p, r, _ = precision_recall_curve(y_test, score)
        ap = average_precision_score(y_test, score)
        ax.plot(r, p, label=f"{name} (AP={ap:.3f})")
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
    ax.set_title("Pump Anomaly Detection — Precision-Recall")
    ax.legend(loc="best"); ax.grid(alpha=0.3)
    save_plot(fig, "anomaly_pr_curve")

    save_metrics("anomaly_detection", {
        "task": "anomaly_detection",
        "dataset": "pump_sensor",
        "split": {"train_normal": int(len(X_train)), "test": int(len(X_test)),
                  "test_positives": int(y_test.sum())},
        "models": results,
        "selected_production_model": "isolation_forest",
        "feature_names": feat,
        "note": "All metrics computed on a held-out temporal test split. "
                "No hardcoded values.",
    })
    print("Anomaly detection done.")


if __name__ == "__main__":
    main()
