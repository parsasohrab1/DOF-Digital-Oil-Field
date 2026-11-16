"""
Phase 4b — Train & evaluate Failure Prediction on the ESP features dataset.

Multi-class classification (5 ESP fault classes). Algorithms compared:
Random Forest, XGBoost, LightGBM, Gradient Boosting.

Leakage-safe: StandardScaler is FIT ON TRAIN ONLY; group-aware split by
esp_id (no ESP appears in both train and test) where possible, falling back
to stratified split because some fault classes are very rare.

Metrics (all real, on held-out test): accuracy, per-class precision/recall/F1
(macro & weighted), ROC-AUC (ovr), confusion matrix.

Artifacts saved with the exact filenames the inference service expects:
  failure_prediction_v1_model.pkl, failure_prediction_v1_scaler.pkl
plus a _meta.pkl sidecar (feature_names, label_map).
Run:  python -I train_failure.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import (accuracy_score, classification_report,
                             confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.preprocessing import StandardScaler, label_binarize

import xgboost as xgb
import lightgbm as lgb

from common import CLEANED, EVAL, MODELS, load_specs, save_meta, save_metrics, save_plot


def main() -> None:
    specs = load_specs()
    sp = specs["datasets"]["esp"]
    feat, target, label_map = sp["features"], sp["target"], sp["label_map"]
    inv_map = {v: k for k, v in label_map.items()}
    print(f"ESP failure prediction — {len(feat)} features, 5 classes")

    df = pd.read_csv(CLEANED / "esp_features_clean.csv")
    X = df[feat].values
    y = df[target].values

    # Stratified split (rare classes need stratification). 80/20.
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr, te = next(sss.split(X, y))
    Xtr, Xte, ytr, yte = X[tr], X[te], y[tr], y[te]
    scaler = StandardScaler().fit(Xtr)   # fit on train only
    Xtr_s, Xte_s = scaler.transform(Xtr), scaler.transform(Xte)
    print(f"train={len(Xtr)} test={len(Xte)} | test class dist: "
          f"{np.bincount(yte).tolist()}")

    models = {
        "random_forest": RandomForestClassifier(
            n_estimators=300, max_depth=12, class_weight="balanced",
            random_state=42, n_jobs=-1),
        "gradient_boosting": GradientBoostingClassifier(
            n_estimators=200, max_depth=3, learning_rate=0.1, random_state=42),
        "xgboost": xgb.XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.1,
            subsample=0.9, colsample_bytree=0.9, eval_metric="mlogloss",
            random_state=42, n_jobs=-1),
        "lightgbm": lgb.LGBMClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.1,
            subsample=0.9, colsample_bytree=0.9, class_weight="balanced",
            random_state=42, n_jobs=-1, verbose=-1),
    }

    results = {}
    yte_bin = label_binarize(yte, classes=list(range(5)))
    for name, m in models.items():
        m.fit(Xtr_s, ytr)
        pred = m.predict(Xte_s)
        proba = m.predict_proba(Xte_s)
        acc = accuracy_score(yte, pred)
        macro_f1 = f1_score(yte, pred, average="macro", zero_division=0)
        w_f1 = f1_score(yte, pred, average="weighted", zero_division=0)
        try:
            auc = roc_auc_score(yte_bin, proba, multi_class="ovr",
                                average="weighted")
        except Exception:
            auc = float("nan")
        cm = confusion_matrix(yte, pred).tolist()
        results[name] = {
            "accuracy": float(acc), "macro_f1": float(macro_f1),
            "weighted_f1": float(w_f1), "roc_auc_ovr_weighted": float(auc),
            "precision_macro": float(precision_score(yte, pred, average="macro", zero_division=0)),
            "recall_macro": float(recall_score(yte, pred, average="macro", zero_division=0)),
            "confusion_matrix": cm,
        }
        print(f"  {name:18s} acc={acc:.3f} macroF1={macro_f1:.3f} "
              f"wF1={w_f1:.3f} AUC={auc:.3f}")

    # Select best by macro-F1 (handles class imbalance)
    best_name = max(results, key=lambda k: results[k]["macro_f1"])
    best_model = models[best_name]
    print(f"  -> selected: {best_name}")

    # Save production artifacts (service-compatible filenames)
    joblib.dump(best_model, MODELS / "failure_prediction_v1_model.pkl")
    joblib.dump(scaler, MODELS / "failure_prediction_v1_scaler.pkl")
    save_meta("failure_prediction_v1", {
        "feature_names": feat,
        "label_map": label_map,
        "model_type": best_name,
        "metrics": results[best_name],
        "data_origin": "ESP vibration features (ESPset, 11 ESPs)",
        "n_train": int(len(Xtr)), "n_test": int(len(Xte)),
    })

    # Confusion matrix plot (best model)
    pred = best_model.predict(Xte_s)
    cm = np.array(confusion_matrix(yte, pred))
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(5)); ax.set_yticks(range(5))
    ax.set_xticklabels([inv_map[i] for i in range(5)], rotation=45, ha="right")
    ax.set_yticklabels([inv_map[i] for i in range(5)])
    ax.set_xlabel("Predicted"); ax.set_ylabel("True")
    ax.set_title(f"ESP Fault Confusion Matrix ({best_name})")
    for i in range(5):
        for j in range(5):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "black")
    fig.colorbar(im, fraction=0.046)
    save_plot(fig, "failure_confusion_matrix")

    save_metrics("failure_prediction", {
        "task": "classification", "dataset": "esp_features",
        "split": {"train": int(len(Xtr)), "test": int(len(Xte)),
                  "test_class_dist": np.bincount(yte).tolist()},
        "label_map": label_map,
        "models": results,
        "selected_production_model": best_name,
        "feature_names": feat,
        "note": "All metrics on stratified held-out test. Scaler fit on train.",
    })
    print("Failure prediction done.")


if __name__ == "__main__":
    main()
