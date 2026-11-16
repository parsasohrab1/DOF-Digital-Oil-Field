# DOF Digital Oil Field — ML Recovery & Backup Manifest
Generated: 2026-11-16 (sandbox session)
Purpose: copy-only inventory of all recoverable datasets, source files, configuration files, and ML artifacts needed to rebuild the 5 ML models (IsolationForest, RandomForest, LSTM x3, RUL, FedAvg).
NOTE: The previously completed commit `2793c9c` and the `ml/` directory were lost when the sandbox recycled and `dof-repo` was freshly re-cloned. No trained artifacts survived. This backup preserves the INPUTS needed to rebuild.
## Summary
- Total recovered files: **32**
- Total size: **96.8 MB** (101491702 bytes)
- `datasets/`: 6 files, 96.6 MB
- `source/`: 13 files, 115.0 KB
- `config/`: 12 files, 60.6 KB
- `artifacts/`: 1 files, 558.0 B

## Recovered Files
| # | Path (in backup) | Size | SHA256 (first 16) | Role |
|---|---|---|---|---|
| 1 | `artifacts/NO_ARTIFACTS_RECOVERED.md` | 558.0 B | `0ecd75833eb0d006` | Manifest note: explains that no trained ML artifacts survived the re-clone |
| 2 | `config/COMPLETE_SETUP.md` | 7.2 KB | `26d5bdd784cebd72` | Complete setup guide |
| 3 | `config/README.md` | 14.8 KB | `7b3fe0bba27cbec3` | Repository README (setup + architecture overview) |
| 4 | `config/SETUP_GUIDE.md` | 12.5 KB | `201bde627f24a31f` | Setup guide |
| 5 | `config/alembic.ini` | 764.0 B | `95ce9d8875f85de1` | Alembic (DB migration) configuration |
| 6 | `config/backend-ci.yml` | 2.1 KB | `6d720db065ed1a56` | Backend CI workflow |
| 7 | `config/ci-cd.yml` | 5.4 KB | `f411d54d06c24e91` | Full CI/CD pipeline workflow |
| 8 | `config/docker-compose.dev.yml` | 11.4 KB | `e5f2760dfc73ff6c` | Dev compose stack (incl. ml-inference-service) |
| 9 | `config/docker-compose.multinode.yml` | 3.3 KB | `39fd1b40f216daa9` | Multinode compose stack |
| 10 | `config/ml-retrain.yml` | 1.3 KB | `322dcc14949a66a1` | ML model retrain workflow (references ml/ artifacts) |
| 11 | `config/pytest.ini` | 554.0 B | `d25270e25a350aa3` | pytest configuration |
| 12 | `config/requirements.txt` | 201.0 B | `8588505941c71f48` | Repo-root Python requirements |
| 13 | `config/smoke-tests.yml` | 1.1 KB | `efce2f16d9ab5d37` | Smoke-test workflow |
| 14 | `datasets/13202_2021_1087_MOESM1_ESM.xlsx` | 303.1 KB | `5cd62b201b3542c6` | Sorush oil-field 7245-sample supplementary dataset (sheet 'SorushField': Sample#, Well, D, Pwh, gamma_o, GLR, QL) — production-prediction / regression dataset |
| 15 | `datasets/archive (1).zip` | 40.4 MB | `156dd6b8c40d28a4` | CWRU bearing 48k load 1: raw *.mat (12 files) + CWRU_48k_load_1_CNN_data.npz + feature_time_48k_2048_load_1.csv — LSTM bearing-fault + IsolationForest dataset |
| 16 | `datasets/archive (2).zip` | 37.1 MB | `5f81ce88a9728ee2` | Industrial sensor time series (sensor.csv, 124 MB uncompressed) — sensor LSTM + FedAvg client partitions |
| 17 | `datasets/archive.zip` | 12.3 MB | `bb97bc5e283c38b8` | NASA C-MAPSS turbofan (CMaps): train/test/RUL FD001-004 + readme + x.txt + Damage Propagation Modeling.pdf — RUL model dataset |
| 18 | `datasets/features.csv` | 658.2 KB | `84184c5852a55c1c` | Engineered Sorush-field features (6032 rows; semicolon CSV; label col) — RandomForest + IsolationForest input |
| 19 | `datasets/s13202-021-01087-4.pdf` | 5.8 MB | `194b7c52b6845309` | Source article (J Petrol Explor Prod Technol) documenting the Sorush field dataset and methodology — reference for the regression model |
| 20 | `source/Dockerfile` | 519.0 B | `3e83ad9afd459a49` | ml-inference-service container build file |
| 21 | `source/__init__.py` | 45.0 B | `3e0c22760c12adb5` | tests package marker |
| 22 | `source/advanced_lstm_model.py` | 14.8 KB | `7f76f2b7e542e87b` | LSTM model class definition (3 LSTM models: bearing fault / sensor / tool-wear) |
| 23 | `source/conftest.py` | 3.6 KB | `2672dc34a3b3d4ce` | pytest fixtures / shared test config |
| 24 | `source/example_lstm_usage.py` | 5.1 KB | `a9c064df293e9651` | LSTM usage example / reference driver |
| 25 | `source/federated_learning.py` | 7.6 KB | `84a8ca98ad91ee0a` | Federated averaging (FedAvg) implementation — client partitions of sensor/features |
| 26 | `source/main.py` | 29.5 KB | `c81ac99bca6683bb` | FastAPI ML inference service + model registry (target of real-model wiring edits) |
| 27 | `source/mlflow_integration.py` | 28.4 KB | `472f7d1f54bb45d2` | MLflow tracking integration (experiment/metrics logging) |
| 28 | `source/requirements.txt` | 467.0 B | `f2903d640ff773ba` | ml-inference-service Python dependencies |
| 29 | `source/requirements.txt` | 70.0 B | `facaf42641079d78` | test dependencies |
| 30 | `source/rul_model.py` | 10.1 KB | `b5c33794c345337e` | RUL (Remaining Useful Life) model definition — trained on CMaps |
| 31 | `source/test_ml_inference_service.py` | 9.7 KB | `a3201c86c03315a1` | ML inference service test suite (target of real-model test edits) |
| 32 | `source/variables_list.csv` | 5.1 KB | `69b5f883a124a865` | DOF tag/variable catalog (66 vars: Pressure/Temperature/Flow ...) — reference schema for sensor features |

## Missing / Not Recovered
- None. All dataset and source inputs required to rebuild the 5 ML models are present.

## Excluded (not ML-relevant, not copied)
- upload/github_token.txt — GitHub credential (never copied/read)
- upload/IMG_20261115_230545_144.jpg, IMG_20261115_231200_769.jpg — reference photos, not ML data
- upload/نامه تضمین انجام تعهدات قرارداد تفاهم نامه.docx — Persian contract document, not ML data
- node_modules/, skills/, dof-repo/.git/ — environment / VCS internals
