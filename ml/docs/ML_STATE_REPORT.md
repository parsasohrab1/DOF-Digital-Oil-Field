# DOF ML — State Report & Real-Data Replacement

This document records the full ML modernization of the DOF (Digital Oil Field)
project: the prior synthetic/mock state, the real datasets used, every model
trained, the real evaluation metrics, the service integration, and the test
results. Branch: `parsa`.

## 1. Prior ML state (before this work)

The ML inference service (`backend/ml-inference-service/`) exposed 19 HTTP
endpoints under `/api/ml-inference/*` but was trained **entirely on synthetic
data** and reported **hardcoded metrics**:

| Model | Algorithm | Training data | Reported metric | Reality |
|---|---|---|---|---|
| anomaly_detection | IsolationForest | `np.random.normal(100,20,(1000,5))` | `accuracy=0.89` | hardcoded literal |
| failure_prediction | RandomForest | `np.random.normal(100,30,(1000,5))`, label `X[:,0]>150` | `f1_score=0.87` | hardcoded literal |
| time_series_forecast | Keras LSTM | synthetic dual-sine wave | `confidence=0.85` | hardcoded literal |
| RUL | RF/GBR/Keras (RULModelManager) | — | `confidence=0.7` (mock) | imported but **never trained or wired to any route** |
| Federated | FedAvg + LogisticRegression | request-body samples | — | real mechanism, demo only |
| Bearing fault | — | — | — | did not exist |
| Sorush QL | — | — | — | did not exist |

Weekly CI (`.github/workflows/ml-retrain.yml`) ran `scripts/train_models.py
--model all` passing **no data**, so every retrain silently retrained on
synthetic defaults. No model artifacts (`.pkl`/`.h5`) were committed — they
were generated at runtime into `/app/models`, so deployments started empty and
fell back to mock models.

Hardcoded-literal locations in the original code: `mlflow_integration.py:115`
(`accuracy=0.89`), `:125`, `:145` (`f1_score=0.87`), `:716`
(`confidence=0.85`); `rul_model.py:183,205`; `advanced_lstm_model.py:383`.

## 2. Real datasets used (6 files, treated independently — never merged)

| Dataset | Origin | Records | Task | Used for |
|---|---|---|---|---|
| `archive.zip` → C-MAPSS FD001 | NASA turbofan **simulation** (public benchmark) | 20,631 rows / 100 engines | regression (RUL) | RUL model |
| `archive (1).zip` → CWRU Bearing | CWRU **laboratory** vibration (public benchmark) | 2,300 rows / 10 fault sub-classes | classification (4 classes) | Bearing fault model |
| `archive (2).zip` → Pump Sensor | **Real industrial** pump sensor log (Kaggle) | 220,320 rows / 152 days | anomaly detection + forecasting | Anomaly + Forecast models |
| `features.csv` → ESP features | ESP vibration-derived features, 11 ESPs | 6,032 rows / 5 fault classes | classification | Failure model + Federated |
| `13202_..._ESM.xlsx` → Sorush field | **Real field** production (Barjouei et al. 2021) | 7,245 rows | regression (QL) | Sorush QL model |
| `s13202-...-4.pdf` | Journal paper | — | reference | Sorush column meaning + benchmark |

Origins are preserved honestly: C-MAPSS is **simulated** (not field oil/gas),
CWRU is **laboratory**, Pump/ESP/Sorush are **real field/industrial**. The
datasets are **never merged** — each model trains on the dataset appropriate to
its task. Cleaned, versioned copies live in `ml/datasets/cleaned/`; the
per-dataset quality report is `ml/evaluation/phase2_data_report.md`; the
feature manifest is `ml/datasets/cleaned/feature_specs.json`.

## 3. Preprocessing (leakage-safe)

For each dataset: drop non-informative columns (C-MAPSS zero-variance sensors
s1/s5/s10/s16/s18/s19 + constant op_set_3; Pump dead sensor_15 + 35%-missing
sensor_50), encode labels, impute (Pump: ffill→median), and split. All splits
are leakage-safe:

- **Temporal** splits for Pump (anomaly + forecast): first 70% train, last 30%
  test, chronologically.
- **Group-aware** split for C-MAPSS RUL: 80 train engines / 20 val engines,
  test = official FD001 held-out set with published true RUL.
- **Stratified** splits for ESP/CWRU (rare classes).
- **Well-stratified** split for Sorush (unseen wells in test).
- Every scaler/encoder is **fit on train only** (`StandardScaler`,
  `MinMaxScaler`).

## 4. Models trained — all with REAL metrics

See `ml/evaluation/ML_EVALUATION_SUMMARY.md` for the full table and
`ml/evaluation/*_metrics.json` for the raw numbers. Headline (all on held-out
test):

| Model | Algorithm | Real metric | Artifact |
|---|---|---|---|
| Anomaly | IsolationForest | P=1.000 R=0.474 F1=0.643 PR-AUC=0.636 FAR=0.0000 | `ml/models/anomaly_detection_v1.pkl` |
| Failure | XGBoost | acc=0.954 macroF1=0.884 AUC=0.989 | `ml/models/failure_prediction_v1_model.pkl` |
| Forecast | Keras stacked LSTM | MAPE=3.03% RMSE=0.0871 (Ridge baseline 0.0644, naive 0.0625) | `ml/models/time_series_forecast_v1_model.h5` |
| RUL | GradientBoosting | RMSE=18.17 MAE=13.06 R²=0.809 | `ml/models/rul_turbofan.pkl` |
| Bearing | LightGBM | acc=0.963 macroF1=0.969 AUC=0.997 | `ml/models/bearing_fault.pkl` |
| Sorush QL | XGBoost | RMSE=461.6 R²=0.9831 MAPE=1.86% | `ml/models/sorush_ql.pkl` |
| Federated | FedAvg + LogisticRegression | global_acc=0.876 (centralized baseline 0.853, 11 nodes) | (in-process, demo script) |

Baselines were compared for every task (statistical / One-Class SVM for
anomaly; Ridge lag + naive persistence for forecast; RF/GBR/XGB/LGBM for the
classification/regression tasks). The best model by held-out performance was
selected per task — not all algorithms were force-used. Per-task plots:
`ml/evaluation/{anomaly_pr_curve, failure_confusion_matrix,
forecast_lstm_actual_vs_pred, rul_pred_vs_true, bearing_confusion_matrix,
sorush_pred_vs_true, before_after}.png`.

## 5. Service integration (contract-preserving)

`backend/ml-inference-service/mlflow_integration.py` was refactored (original
backed up to `ml/backups/mlflow_integration.py.orig`):

1. **mlflow is now optional** (`import mlflow` in try/except). The service
   loads REAL committed artifacts and serves inference with no MLflow server.
2. **Local-artifact fallback**: `load_model` tries the MLflow registry, then
   falls back to the committed `ml/models/*.pkl`/`.h5`. `_load_local_model`
   handles both joblib (sklearn) and Keras `.h5`.
3. **Trainers use real data**: `train_anomaly_detection_model`,
   `train_failure_prediction_model`, `train_time_series_model` now load real
   cleaned data from `ml/datasets/cleaned/` when called with no arguments — no
   more `np.random` defaults.
4. **Hardcoded metrics removed**: `accuracy=0.89`, `f1_score=0.87`,
   `confidence=0.85` are replaced with **computed** validation metrics
   (precision/recall/F1/PR-AUC/FAR for anomaly; accuracy/macro-F1/ROC-AUC for
   failure; test loss/MAE for forecast). Confidence is **derived** from
   validation MAE.
5. **Feature-name selection at predict**: `predict_anomaly`/`predict_failure`
   select features by name (from the `_meta.pkl` sidecar) in trained order, so
   the model receives exactly the features it was trained on regardless of
   dict ordering — robust without changing the `features: Dict[str,float]`
   contract.
6. **Writable-path fallback** in `__init__`: if `MODEL_STORAGE_PATH`
   (`/app/models`) is not writable, falls back to the repo `ml/models/` so the
   service starts instead of crashing.

No Pydantic model, endpoint path, request schema, or response schema was
changed. The frontend `mlAPI`/`federatedAPI` contracts are untouched. Two
small robustness fixes in `main.py`: `except HTTPException: raise` (so a 400
for unknown model type is no longer swallowed into a 500), and the prometheus
metric block catches `Exception` (not just `ImportError`) so re-importing
main.py in tests does not crash on duplicate metric registration.

`backend/ml-inference-service/smoke_test_service.py` verifies all 3 service
models load from local REAL artifacts and serve inference (no MLflow needed).

## 6. Tests

`backend/tests/test_ml_inference_service.py` (existing, 10 tests: drift, A/B,
federated) — **all pass** after refactoring.
`backend/tests/test_ml_real_integration.py` (new, 8 tests: health,
models-loaded-from-local, infer anomaly/failure, forecast derived confidence,
missing-feature edge case, short-history edge case, unknown model type) —
**all pass**.

Run: `python -m pytest tests/test_ml_inference_service.py
tests/test_ml_real_integration.py --noconftest --override-ini="addopts=" -p no:ddtrace`
→ **18 passed**.

## 7. Outputs in the repository

```
ml/
├── datasets/
│   ├── cleaned/            # cleaned, versioned datasets + feature_specs.json
│   └── raw/                # extracted source archives (gitignored-large where needed)
├── models/                 # committed REAL model artifacts (.pkl/.h5 + _meta.pkl sidecars)
├── evaluation/             # metrics JSON, plots, phase2 report, summary
├── training/               # preprocessing + per-task training scripts + summary builder
├── backups/                # original service files (.orig) before refactoring
└── docs/                   # this report + README
```

## 8. Known limitations (honest)

- **RUL model is trained but not HTTP-exposed**: the original service imports
  `RULModelManager` but never wires it to a route (frontend `/rul/*` calls are
  dead). Exposing it would require adding endpoints — a contract change that is
  **forbidden without approval**. The trained artifact + scaler + meta are
  committed (`ml/models/rul_turbofan*`) and the `RULModelManager.predict_rul`
  API works; a route can be added later with explicit approval.
- **Bearing & Sorush models are standalone**: no service endpoint exists for
  them. They are delivered as trained, evaluated artifacts with full metrics,
  ready to wire in when a route is approved.
- **Forecast R² is negative** on the Pump sensor_00 test window (near-constant
  target); MAPE/MAE are the meaningful metrics. A naive persistence baseline
  slightly beats the LSTM on this stable channel. The LSTM ships as the
  Keras-compatible artifact for the `/forecast` contract.
- **C-MAPSS RUL** uses simulated turbofan data (NASA benchmark), not field
  oil/gas measurements — validates methodology, not field performance.

## 9. Rollback

Original service files are preserved in `ml/backups/`:
`mlflow_integration.py.orig`, `rul_model.py.orig`,
`advanced_lstm_model.py.orig`, `train_models.py.orig`. To roll back, restore
these to `backend/ml-inference-service/` (and `scripts/`) and delete the
`ml/models/*` artifacts — the service reverts to its prior behavior.
