"""
Phase 3 — Preprocessing & feature engineering for all DOF datasets.

Produces cleaned, versioned datasets under ml/datasets/cleaned/ and a single
feature-spec manifest (ml/datasets/cleaned/feature_specs.json) that the
training scripts AND the inference service both reference, so the feature
vector order/names seen at training == the order/names expected at inference.

Anti-leakage rules enforced here:
  * All scaling/encoding artifacts are FIT ON TRAIN ONLY inside the training
    scripts (this script only cleans/encodes/splits; it does not fit scalers).
  * Time-series splits respect temporal order (train=earliest, test=latest).
  * Group-aware splits where leakage could occur (RUL: split by engine unit).

Raw files are left untouched.
Run:  python -I preprocess.py
"""

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("/home/z/my-project/dof-repo/ml/datasets/raw")
OUT = Path("/home/z/my-project/dof-repo/ml/datasets/cleaned")
OUT.mkdir(parents=True, exist_ok=True)

SPECS: dict = {"datasets": {}}


def save_csv(df: pd.DataFrame, name: str) -> Path:
    p = OUT / name
    df.to_csv(p, index=False)
    print(f"  [saved] {p}  ({len(df):,} rows × {df.shape[1]} cols, "
          f"{os.path.getsize(p)/1024:.0f} KB)")
    return p


# ---------------------------------------------------------------------------
# 1) C-MAPSS FD001  (RUL regression)
# ---------------------------------------------------------------------------
def preprocess_cmapss() -> None:
    print("\n[1/6] C-MAPSS FD001")
    base = RAW / "cmapss" / "CMaps"
    cols = (["unit", "time"] + [f"op_set_{i}" for i in (1, 2, 3)]
            + [f"s{i}" for i in range(1, 22)])
    train = pd.read_csv(base / "train_FD001.txt", sep=r"\s+", header=None,
                        names=cols, engine="python")
    test = pd.read_csv(base / "test_FD001.txt", sep=r"\s+", header=None,
                       names=cols, engine="python")
    rul_test = pd.read_csv(base / "RUL_FD001.txt", header=None, names=["RUL"])

    # RUL label for train: cycles remaining until end-of-life per unit
    eol = train.groupby("unit")["time"].max()
    train["RUL"] = train["unit"].map(eol) - train["time"]
    # RUL label for test: true RUL at last observed cycle per unit
    test_last = test.groupby("unit").tail(1).copy()
    test_last["RUL"] = rul_test["RUL"].values

    # Drop non-informative (zero / near-zero variance) columns discovered in P2
    drop = ["op_set_3", "s1", "s5", "s10", "s16", "s18", "s19"]
    train = train.drop(columns=drop)
    test_last = test_last.drop(columns=drop)

    features = [c for c in train.columns if c not in ("unit", "time", "RUL")]
    save_csv(train, "cmapss_fd001_train.csv")
    save_csv(test_last, "cmapss_fd001_test.csv")

    # Engine-unit-aware split for validation (80 units train / 20 val)
    units = sorted(train["unit"].unique())
    val_units = units[80:]
    val_mask = train["unit"].isin(val_units)
    val_df = train[val_mask].copy()
    tr_df = train[~val_mask].copy()
    save_csv(tr_df, "cmapss_fd001_train_split.csv")
    save_csv(val_df, "cmapss_fd001_val_split.csv")

    SPECS["datasets"]["cmapss"] = {
        "task": "regression", "target": "RUL", "features": features,
        "group_col": "unit",
        "origin": "NASA C-MAPSS turbofan simulation (public benchmark)",
        "note": "SIMULATED degradation — not field oil/gas measurements; "
                "valid for RUL methodology.",
    }
    print(f"  features({len(features)}): {features}")


# ---------------------------------------------------------------------------
# 2) CWRU Bearing  (fault classification, 4 classes)
# ---------------------------------------------------------------------------
def preprocess_cwru() -> None:
    print("\n[2/6] CWRU Bearing")
    df = pd.read_csv(RAW / "cwru" / "feature_time_48k_2048_load_1.csv")
    # Map 10 detailed fault strings -> 4 categories
    cat = (df["fault"].str.split("_").str[0]
           .map({"Normal": "Normal", "IR": "InnerRace",
                 "OR": "OuterRace", "Ball": "Ball"}))
    df["fault_category"] = cat
    label_map = {"Normal": 0, "InnerRace": 1, "OuterRace": 2, "Ball": 3}
    df["label"] = df["fault_category"].map(label_map)
    features = ["max", "min", "mean", "sd", "rms", "skewness",
                "kurtosis", "crest", "form"]
    df = df[features + ["label", "fault"]]
    save_csv(df, "cwru_bearing_clean.csv")

    SPECS["datasets"]["cwru"] = {
        "task": "classification", "target": "label", "features": features,
        "label_map": label_map,
        "origin": "CWRU bearing test-rig laboratory data (public benchmark)",
        "note": "LABORATORY vibration measurements — real measured accelerations.",
    }
    print(f"  label dist: {df['label'].value_counts().to_dict()}")


# ---------------------------------------------------------------------------
# 3) Pump Sensor  (anomaly detection + LSTM forecasting)
# ---------------------------------------------------------------------------
def preprocess_pump() -> None:
    print("\n[3/6] Pump Sensor")
    df = pd.read_csv(RAW / "pump" / "sensor.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Drop dead sensor_15 (99.9% missing) and sensor_50 (35% missing)
    drop = ["sensor_15", "sensor_50"]
    sensor_cols = [c for c in df.columns if c.startswith("sensor_")
                   and c not in drop]

    # Forward-fill then median-impute remaining gaps (time-ordered)
    df[sensor_cols] = (df[sensor_cols].ffill()
                       .fillna(df[sensor_cols].median()))

    # Anomaly label: BROKEN + RECOVERING == anomaly (1), NORMAL == 0
    df["anomaly"] = (df["machine_status"] != "NORMAL").astype(int)

    # Pick the most informative low-missing sensor for univariate forecasting.
    # Use sensor_00 (pump pressure-like) after imputation; verified stable trend.
    forecast_col = "sensor_00"
    assert forecast_col in df.columns

    df_out = df[["timestamp"] + sensor_cols + ["machine_status", "anomaly"]]
    # Save full cleaned set as gzip CSV (no parquet dep; numpy 1.x compatible)
    pq = OUT / "pump_sensor_clean.csv.gz"
    df_out.to_csv(pq, index=False, compression="gzip")
    print(f"  [saved] {pq}  ({len(df_out):,} rows × {df_out.shape[1]} cols, "
          f"{os.path.getsize(pq)/1024/1024:.1f} MB)")

    # Save the univariate forecasting series (timestamp + sensor_00)
    fc = df[["timestamp", forecast_col]].copy()
    fc.columns = ["timestamp", "value"]
    fc_path = save_csv(fc, "pump_forecast_series.csv")

    SPECS["datasets"]["pump"] = {
        "task": "anomaly_detection+forecasting",
        "anomaly_target": "anomaly",
        "forecast_col": forecast_col,
        "features": sensor_cols,
        "origin": "Real industrial pump sensor log (public Kaggle dataset)",
        "note": "FIELD-like time-series with documented breakdown events.",
    }
    print(f"  anomaly dist: {df['anomaly'].value_counts().to_dict()}")
    print(f"  sensors kept: {len(sensor_cols)} (dropped {drop})")


# ---------------------------------------------------------------------------
# 4) ESP features  (multi-class failure classification + federated)
# ---------------------------------------------------------------------------
def preprocess_esp() -> None:
    print("\n[4/6] ESP Features")
    df = pd.read_csv(RAW / "esp" / "features.csv", sep=";")
    label_map = {"Normal": 0, "Unbalance": 1, "Faulty sensor": 2,
                 "Rubbing": 3, "Misalignment": 4}
    df["label_id"] = df["label"].map(label_map)
    features = ["median(8,13)", "rms(98,102)", "median(98,102)",
                "peak1x", "peak2x", "a", "b"]
    df = df[["id", "esp_id"] + features + ["label", "label_id"]]
    save_csv(df, "esp_features_clean.csv")

    SPECS["datasets"]["esp"] = {
        "task": "classification", "target": "label_id", "features": features,
        "group_col": "esp_id", "label_map": label_map,
        "origin": "ESP vibration-derived features (ESPset, 11 ESPs)",
        "note": "Real ESP fault classes from vibration feature extraction.",
    }
    print(f"  esp_id count: {df['esp_id'].nunique()} | "
          f"label dist: {df['label_id'].value_counts().to_dict()}")


# ---------------------------------------------------------------------------
# 5) Sorush field  (QL regression)
# ---------------------------------------------------------------------------
def preprocess_sorush() -> None:
    print("\n[5/6] Sorush Field")
    # Sheet layout (A1:J7248): row0=title, row1=column names, row2=units,
    # rows 3..end = data. Cols A-G are the 7 data fields; H-J are metadata.
    raw = pd.read_excel(RAW / "sorush" / "sorush_field.xlsx",
                        sheet_name="SorushField", header=None)
    df = raw.iloc[3:, 0:7].copy()
    df.columns = ["sample", "well", "choke_d64", "pwh_psig",
                  "oil_gravity", "glr_scf_stb", "ql_stb_d"]
    df = df.reset_index(drop=True)
    for c in ["sample", "choke_d64", "pwh_psig", "oil_gravity",
              "glr_scf_stb", "ql_stb_d"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["well"] = df["well"].astype(str).str.strip()
    df = df.dropna(subset=["ql_stb_d"]).reset_index(drop=True)
    # Encode well as integer code (metadata for grouped eval)
    df["well_code"] = df["well"].astype("category").cat.codes
    features = ["choke_d64", "pwh_psig", "oil_gravity", "glr_scf_stb"]
    df = df[["sample", "well", "well_code"] + features + ["ql_stb_d"]]
    save_csv(df, "sorush_field_clean.csv")

    SPECS["datasets"]["sorush"] = {
        "task": "regression", "target": "ql_stb_d", "features": features,
        "origin": "Sorush oil field production records (Barjouei et al. 2021, "
                  "J. Pet. Explor. Prod. Technol.) — REAL field data.",
        "benchmark": {"paper_RMSE_STB_D": 196, "paper_R2": 0.9969,
                      "algorithms_compared": "DL > DT > RF > ANN > SVR"},
    }
    print(f"  wells: {df['well'].nunique()} | QL range: "
          f"[{df['ql_stb_d'].min():.0f}, {df['ql_stb_d'].max():.0f}] STB/D")


def main() -> None:
    print("Phase 3 — preprocessing all datasets (raw untouched)...")
    for fn in (preprocess_cmapss, preprocess_cwru, preprocess_pump,
               preprocess_esp, preprocess_sorush):
        try:
            fn()
        except Exception as e:
            print(f"  ERROR in {fn.__name__}: {type(e).__name__}: {e}")
            raise
    spec_path = OUT / "feature_specs.json"
    spec_path.write_text(json.dumps(SPECS, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    print(f"\n[written] {spec_path}")
    print("Phase 3 complete.")


if __name__ == "__main__":
    main()
