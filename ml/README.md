# `ml/` — DOF Machine Learning assets

Real-data ML models, datasets, training code, evaluation and documentation for
the DOF project. See [`docs/ML_STATE_REPORT.md`](docs/ML_STATE_REPORT.md) for
the full state report.

## Layout

| Path | Contents |
|---|---|
| `datasets/cleaned/` | Cleaned, versioned datasets + `feature_specs.json` (the feature manifest shared by training and the inference service) |
| `datasets/raw/` | Extracted source archives (large files gitignored where needed) |
| `models/` | Committed REAL model artifacts (`.pkl`/`.h5`) + `_meta.pkl` sidecars (feature_names, label_map, metrics, derived_confidence) |
| `evaluation/` | Per-task `*_metrics.json`, plots, `phase2_data_report.md`, `ML_EVALUATION_SUMMARY.md`, `before_after.png` |
| `training/` | `preprocess.py` + per-task `train_*.py` + `make_evaluation_summary.py` + `common.py` |
| `backups/` | Original service files (`.orig`) before refactoring |
| `docs/` | `ML_STATE_REPORT.md` and this README |

## Reproduce

```bash
# 1. Place the 6 source files under ml/datasets/raw/ (see feature_specs.json)
# 2. Preprocess
python -I ml/training/preprocess.py
# 3. Train every model (real metrics, artifacts saved to ml/models/)
python -I ml/training/train_anomaly.py
python -I ml/training/train_failure.py
python -I ml/training/train_forecast.py
python -I ml/training/train_rul.py
python -I ml/training/train_bearing.py
python -I ml/training/train_sorush.py
python -I ml/training/train_federated.py
# 4. Build the consolidated evaluation report
python -I ml/training/make_evaluation_summary.py
```

## Service integration

The inference service (`backend/ml-inference-service/`) loads the committed
artifacts in `ml/models/` directly (no MLflow server required). Verified by:

```bash
cd backend/ml-inference-service && python -I smoke_test_service.py
```

## Tests

```bash
cd backend && python -m pytest tests/test_ml_inference_service.py \
    tests/test_ml_real_integration.py --noconftest --override-ini="addopts=" -p no:ddtrace
# 18 passed
```
