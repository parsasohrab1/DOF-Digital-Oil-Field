"""
Group-based evaluation of the SorushField QL model and the ESP fault classifier.

Both models already exist in this repository (trained by ml/training/ on real
data, single stratified/random splits). This script adds the group-based
generalization evaluation that those single-split numbers cannot show:

  SorushField QL  - Leave-One-Well-Out (LOWO) cross-validation over the 10
                    wells, raw features vs engineered choke-flow features.
  ESP faults      - GroupKFold(5) over esp_id + Leave-One-ESP-Out, with a
                    per-device breakdown and the minority-class (Misalignment)
                    recall tracked explicitly.

Datasets (provenance):
  sorush_field_clean.csv - REAL historical oil-field measurements (Sorush
                    field, Barjouei et al. 2021 supplementary data). NOT live.
  esp_features_clean.csv - LABORATORY vibration-derived ESP features
                    (11 devices). NOT oil-field and NOT live data.

Outputs (repo-relative):
  ml/evaluation/sorush_lowo_report.json
  ml/evaluation/esp_group_validation_report.json
  ml/models/sorush_ql_lowo_model.joblib   (final model, all wells)
  ml/models/sorush_ql_lowo_spec.json
  ml/models/esp_classifier_group_model.joblib
  ml/models/esp_classifier_group_spec.json

Run:
  cd <repo root>
  python ml/training/evaluate_group_generalization.py
"""

import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    recall_score,
)
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "ml" / "evaluation"
MODELS_DIR = ROOT / "ml" / "models"
RANDOM_STATE = 42


# --------------------------------------------------------------------------- #
# SorushField QL — Leave-One-Well-Out
# --------------------------------------------------------------------------- #
SORUSH_BASE_FEATURES = ["choke_d64", "pwh_psig", "oil_gravity", "glr_scf_stb"]
SORUSH_ENGINEERED = [
    "choke_d64",
    "pwh_psig",
    "oil_gravity",
    "glr_scf_stb",
    "D_sq",            # choke area proxy ~ D^2
    "D_sqrt_Pwh",      # D * sqrt(Pwh): simplified Gilbert-type choke term
    "Pwh_per_GLR",     # pressure per unit gas ratio
    "GLR_per_D",
    "log_GLR",
    "gamma_x_GLR",
]


def add_sorush_engineered(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    D = df["choke_d64"]
    Pwh = df["pwh_psig"]
    GLR = df["glr_scf_stb"]
    gam = df["oil_gravity"]
    df["D_sq"] = D ** 2
    df["D_sqrt_Pwh"] = D * np.sqrt(Pwh)
    df["Pwh_per_GLR"] = Pwh / GLR
    df["GLR_per_D"] = GLR / D
    df["log_GLR"] = np.log(GLR)
    df["gamma_x_GLR"] = gam * GLR
    return df


def lowo_eval(df: pd.DataFrame, features: list) -> dict:
    """Leave-One-Well-Out CV with an ExtraTrees regressor (seeded)."""
    y = df["ql_stb_d"].values
    groups = df["well"].values
    logo = LeaveOneGroupOut()
    per_well = {}
    maes, rmses, r2s = [], [], []
    for tr_idx, te_idx in logo.split(df, y, groups=groups):
        well = str(groups[te_idx][0])
        model = ExtraTreesRegressor(
            n_estimators=300, min_samples_leaf=2, random_state=RANDOM_STATE, n_jobs=-1
        )
        model.fit(df.iloc[tr_idx][features], y[tr_idx])
        pred = model.predict(df.iloc[te_idx][features])
        mae = float(mean_absolute_error(y[te_idx], pred))
        rmse = float(np.sqrt(mean_squared_error(y[te_idx], pred)))
        r2 = float(r2_score(y[te_idx], pred))
        maes.append(mae)
        rmses.append(rmse)
        r2s.append(r2)
        per_well[well] = {
            "mae": mae,
            "rmse": rmse,
            "r2": r2,
            "n_test": int(len(te_idx)),
            "n_train": int(len(tr_idx)),
            "y_mean": float(np.mean(y[te_idx])),
            "y_std": float(np.std(y[te_idx])),
        }
    return {
        "overall": {
            "mae": float(np.mean(maes)),
            "rmse": float(np.mean(rmses)),
            "r2": float(np.mean(r2s)),
        },
        "per_well": per_well,
    }


def evaluate_sorush() -> dict:
    df = pd.read_csv(ROOT / "ml" / "datasets" / "cleaned" / "sorush_field_clean.csv")
    wells = sorted(df["well"].unique())
    print(f"[Sorush] {len(df)} rows, {len(wells)} wells: {wells}")

    base = lowo_eval(df, SORUSH_BASE_FEATURES)
    df_eng = add_sorush_engineered(df)
    eng = lowo_eval(df_eng, SORUSH_ENGINEERED)
    delta_mae = eng["overall"]["mae"] - base["overall"]["mae"]
    rel_pct = 100.0 * delta_mae / base["overall"]["mae"]

    # Final model: engineered features, all wells (LOWO estimates its
    # generalization to a NEW well; the deployed artifact uses all data).
    final = ExtraTreesRegressor(
        n_estimators=300, min_samples_leaf=2, random_state=RANDOM_STATE, n_jobs=-1
    )
    final.fit(df_eng[SORUSH_ENGINEERED], df_eng["ql_stb_d"])

    model_path = MODELS_DIR / "sorush_ql_lowo_model.joblib"
    joblib.dump(final, model_path)
    spec = {
        "model": "ExtraTreesRegressor(n_estimators=300, min_samples_leaf=2)",
        "features": SORUSH_ENGINEERED,
        "target": "ql_stb_d",
        "group": "well",
        "validation": "Leave-One-Well-Out (10 folds)",
        "feature_engineering": "choke-flow terms (D^2, D*sqrt(Pwh), Pwh/GLR, GLR/D, log GLR, gamma*GLR)",
        "lowo_overall": eng["overall"],
        "baseline_raw_features": base["overall"],
        "delta_mae_vs_raw_features": delta_mae,
        "relative_delta_pct": rel_pct,
        "random_state": RANDOM_STATE,
        "dataset": "ml/datasets/cleaned/sorush_field_clean.csv",
        "provenance": "Real historical measured oil-field data (Sorush field, "
        "Barjouei et al. 2021 supplementary data). NOT live data.",
    }
    with open(MODELS_DIR / "sorush_ql_lowo_spec.json", "w") as fh:
        json.dump(spec, fh, indent=2)

    report = {
        "dataset": "sorush_field_clean.csv",
        "provenance": spec["provenance"],
        "n_rows": int(len(df)),
        "wells": wells,
        "features_raw": SORUSH_BASE_FEATURES,
        "features_engineered": SORUSH_ENGINEERED,
        "validation": "Leave-One-Well-Out",
        "model": "ExtraTreesRegressor",
        "baseline_raw": base,
        "engineered": eng,
        "delta_mae": delta_mae,
        "relative_delta_pct": rel_pct,
        "engineered_better": bool(delta_mae < 0),
        "final_model": str(model_path.relative_to(ROOT)),
    }
    with open(EVAL_DIR / "sorush_lowo_report.json", "w") as fh:
        json.dump(report, fh, indent=2)
    print(
        f"[Sorush] LOWO raw MAE={base['overall']['mae']:.1f} -> "
        f"engineered MAE={eng['overall']['mae']:.1f} "
        f"({rel_pct:+.2f}%); final model saved: {model_path.name}"
    )
    return report


# --------------------------------------------------------------------------- #
# ESP fault classifier — GroupKFold(5) + Leave-One-ESP-Out
# --------------------------------------------------------------------------- #
ESP_FEATURES = [
    "median(8,13)", "rms(98,102)", "median(98,102)", "peak1x", "peak2x", "a", "b",
]
# XGBoost was the best model in the earlier single-split evaluation; it is kept
# as the primary model here, with a balanced RandomForest as the reference.


def evaluate_esp() -> dict:
    df = pd.read_csv(ROOT / "ml" / "datasets" / "cleaned" / "esp_features_clean.csv")
    X = df[ESP_FEATURES].values
    y = df["label_id"].values
    groups = df["esp_id"].values
    classes = sorted(df["label"].unique())
    label_names = {int(df[df["label"] == c]["label_id"].iloc[0]): c for c in classes}
    minority_label = "Misalignment"
    minority_id = int(df[df["label"] == minority_label]["label_id"].iloc[0])
    print(f"[ESP] {len(df)} rows, {df['esp_id'].nunique()} devices, classes: {classes}")

    def make_xgb():
        from xgboost import XGBClassifier

        return XGBClassifier(
            n_estimators=400,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=RANDOM_STATE,
            eval_metric="mlogloss",
            n_jobs=-1,
        )

    def make_rf():
        return RandomForestClassifier(
            n_estimators=400,
            class_weight="balanced_subsample",
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )

    # --- GroupKFold(5) over esp_id -----------------------------------------
    gkf = GroupKFold(n_splits=5)
    gkf_results = {}
    for name, factory in (("XGBoost", make_xgb), ("RandomForest_balanced", make_rf)):
        f1s, baccs, accs, min_recalls = [], [], [], []
        for tr_idx, te_idx in gkf.split(X, y, groups):
            model = factory()
            model.fit(X[tr_idx], y[tr_idx])
            pred = model.predict(X[te_idx])
            f1s.append(f1_score(y[te_idx], pred, average="macro"))
            baccs.append(balanced_accuracy_score(y[te_idx], pred))
            accs.append(accuracy_score(y[te_idx], pred))
            rec = recall_score(
                y[te_idx], pred, labels=[minority_id], average=None,
                zero_division=0,
            )
            min_recalls.append(float(rec[0]) if len(rec) else 0.0)
        gkf_results[name] = {
            "macro_f1": float(np.mean(f1s)),
            "balanced_accuracy": float(np.mean(baccs)),
            "accuracy": float(np.mean(accs)),
            "minority_recall_misalignment": float(np.mean(min_recalls)),
        }
        print(
            f"[ESP] GroupKFold5 {name}: macroF1={gkf_results[name]['macro_f1']:.3f} "
            f"bal_acc={gkf_results[name]['balanced_accuracy']:.3f} "
            f"min_recall={gkf_results[name]['minority_recall_misalignment']:.3f}"
        )

    # --- Leave-One-ESP-Out with the best model ------------------------------
    logo = LeaveOneGroupOut()
    per_device = {}
    y_true_all, y_pred_all = [], []
    for tr_idx, te_idx in logo.split(X, y, groups):
        dev = str(groups[te_idx][0])
        model = make_xgb()
        model.fit(X[tr_idx], y[tr_idx])
        pred = model.predict(X[te_idx])
        y_true_all.extend(y[te_idx].tolist())
        y_pred_all.extend(pred.tolist())
        per_device[dev] = {
            "balanced_accuracy": float(balanced_accuracy_score(y[te_idx], pred)),
            "n_test": int(len(te_idx)),
        }
    y_true_all = np.array(y_true_all)
    y_pred_all = np.array(y_pred_all)
    loo = {
        "balanced_accuracy": float(balanced_accuracy_score(y_true_all, y_pred_all)),
        "macro_f1": float(f1_score(y_true_all, y_pred_all, average="macro")),
        "accuracy": float(accuracy_score(y_true_all, y_pred_all)),
        "minority_recall_misalignment": float(
            recall_score(
                y_true_all, y_pred_all, labels=[minority_id], average=None,
                zero_division=0,
            )[0]
        ),
        "per_device": per_device,
    }
    worst = min(per_device.items(), key=lambda kv: kv[1]["balanced_accuracy"])
    print(
        f"[ESP] LOO: bal_acc={loo['balanced_accuracy']:.3f} macroF1={loo['macro_f1']:.3f} "
        f"min_recall={loo['minority_recall_misalignment']:.3f}; "
        f"worst device: esp {worst[0]} ({worst[1]['balanced_accuracy']:.3f})"
    )

    # --- Final model on all data -------------------------------------------
    final = make_xgb()
    final.fit(X, y)
    model_path = MODELS_DIR / "esp_classifier_group_model.joblib"
    joblib.dump(final, model_path)
    spec = {
        "model": "XGBClassifier(n_estimators=400, max_depth=6, lr=0.1)",
        "features": ESP_FEATURES,
        "target": "label_id",
        "label_names": {str(k): v for k, v in label_names.items()},
        "group": "esp_id",
        "validation": "GroupKFold(5) + Leave-One-ESP-Out",
        "groupkfold": gkf_results["XGBoost"],
        "leave_one_esp_out": {
            k: loo[k] for k in ("balanced_accuracy", "macro_f1", "accuracy",
                                "minority_recall_misalignment")
        },
        "worst_device": {"esp_id": worst[0], **worst[1]},
        "random_state": RANDOM_STATE,
        "dataset": "ml/datasets/cleaned/esp_features_clean.csv",
        "provenance": "Laboratory vibration-derived ESP features (11 devices). "
        "NOT live oil-field data.",
    }
    with open(MODELS_DIR / "esp_classifier_group_spec.json", "w") as fh:
        json.dump(spec, fh, indent=2)

    report = {
        "dataset": "esp_features_clean.csv",
        "provenance": spec["provenance"],
        "n_rows": int(len(df)),
        "n_devices": int(df["esp_id"].nunique()),
        "features": ESP_FEATURES,
        "group": "esp_id",
        "label_counts": {c: int((df["label"] == c).sum()) for c in classes},
        "minority_class": minority_label,
        "groupkfold_results": gkf_results,
        "leave_one_esp_out": loo,
        "classification_report": classification_report(
            y_true_all, y_pred_all,
            target_names=[label_names[i] for i in sorted(label_names)],
            output_dict=True, zero_division=0,
        ),
        "final_model": str(model_path.relative_to(ROOT)),
    }
    with open(EVAL_DIR / "esp_group_validation_report.json", "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"[ESP] final model saved: {model_path.name}")
    return report


if __name__ == "__main__":
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    evaluate_sorush()
    evaluate_esp()
    print(f"done in {time.time() - t0:.1f}s")
