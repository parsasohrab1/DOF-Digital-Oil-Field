"""
Phase 2 — Independent quality & suitability analysis of each DOF input dataset.

For every dataset we report: records, features, dtypes, missing values,
duplicates, outliers (IQR), distribution summary (min/max/mean/std), units,
value ranges, labels, the suitable ML task, and the dataset's origin/validity.

Datasets are analyzed INDEPENDENTLY. No merging. Raw files are left untouched.

Run:  python -I phase2_data_analysis.py
"""

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("/home/z/my-project/dof-repo/ml/datasets/raw")
OUT = Path("/home/z/my-project/dof-repo/ml/evaluation")
OUT.mkdir(parents=True, exist_ok=True)

REPORT_LINES: list[str] = []


def line(s: str = "") -> None:
    REPORT_LINES.append(s)
    print(s)


def section(title: str) -> None:
    line()
    line(f"## {title}")
    line()


def outliers_iqr(df: pd.DataFrame) -> dict:
    out = {}
    num = df.select_dtypes(include=[np.number])
    for c in num.columns:
        q1, q3 = num[c].quantile(0.25), num[c].quantile(0.75)
        iqr = q3 - q1
        if iqr == 0 or pd.isna(iqr):
            out[c] = 0
            continue
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        out[c] = int(((num[c] < lo) | (num[c] > hi)).sum())
    return out


def summarize(name: str, df: pd.DataFrame, origin: str, task: str,
              units: dict | None = None, label_col: str | None = None) -> None:
    section(f"Dataset: {name}")
    line(f"- **Origin / validity**: {origin}")
    line(f"- **Suitable ML task**: {task}")
    line(f"- **Records**: {len(df):,}")
    line(f"- **Columns**: {df.shape[1]}")
    line(f"- **Dtypes**: {dict(df.dtypes.astype(str))}")
    miss = df.isna().sum()
    miss = miss[miss > 0]
    line(f"- **Missing values**: {dict(miss.astype(int)) if len(miss) else 'none'}")
    line(f"- **Duplicate rows**: {int(df.duplicated().sum())}")
    if label_col and label_col in df.columns:
        ld = df[label_col].value_counts(dropna=False)
        line(f"- **Label distribution (`{label_col}`)**: {ld.to_dict()}")
    if units:
        line(f"- **Units**: {units}")
    num = df.select_dtypes(include=[np.number])
    if not num.empty:
        desc = num.describe().T[["min", "max", "mean", "std"]].round(4)
        line(f"- **Numeric ranges (min/max/mean/std)**:")
        for c in desc.index:
            r = desc.loc[c]
            line(f"    - {c}: min={r['min']} max={r['max']} mean={r['mean']} std={r['std']}")
        ol = outliers_iqr(df)
        top5 = sorted(ol.items(), key=lambda kv: kv[1], reverse=True)[:5]
        line(f"- **Outliers (IQR, top-5 cols)**: {dict(top5)}")


# ---------------------------------------------------------------------------
# 1) C-MAPSS (NASA Turbofan) — archive.zip
# ---------------------------------------------------------------------------
def analyze_cmapss() -> None:
    base = RAW / "cmapss" / "CMaps"
    cols = (["unit", "time"] + [f"op_set_{i}" for i in (1, 2, 3)]
            + [f"s{i}" for i in range(1, 22)])
    df = pd.read_csv(base / "train_FD001.txt", sep=r"\s+", header=None,
                     names=cols, engine="python")
    # RUL label: cycles remaining until end-of-life for each unit
    eol = df.groupby("unit")["time"].max()
    df["RUL"] = df["unit"].map(eol) - df["time"]
    summarize(
        "C-MAPSS FD001 (NASA Turbofan Degradation)",
        df.drop(columns=["RUL"]),
        origin="NASA C-MAPSS turbofan simulation (public benchmark). SIMULATED "
               "engine degradation — NOT field oil/gas measurements. Validated "
               "for RUL methodology.",
        task="Regression — Remaining Useful Life (RUL) prediction from sensor "
             "and operating-setting trajectories.",
        units={"time": "cycles", "op_set_1/2/3": "normalized", "s1..s21": "raw sensor"},
        label_col=None,
    )
    line(f"- **RUL target stats**: min={int(df['RUL'].min())} max={int(df['RUL'].max())} "
         f"mean={df['RUL'].mean():.1f}")
    line(f"- **Units (engines)**: {df['unit'].nunique()}  |  "
         f"avg cycles/unit: {df.groupby('unit').size().mean():.0f}")
    # test RUL ground truth
    rul_test = pd.read_csv(base / "RUL_FD001.txt", header=None, names=["RUL"])
    line(f"- **Test-set true RUL**: {len(rul_test)} engines, "
         f"range [{int(rul_test['RUL'].min())}, {int(rul_test['RUL'].max())}]")
    line("- **Sensors with zero variance (non-informative)**: "
         f"{[c for c in cols[5:] if df[c].std() < 1e-8]}")


# ---------------------------------------------------------------------------
# 2) CWRU Bearing — archive (1).zip
# ---------------------------------------------------------------------------
def analyze_cwru() -> None:
    csv = RAW / "cwru" / "feature_time_48k_2048_load_1.csv"
    df = pd.read_csv(csv)
    label = "fault" if "fault" in df.columns else df.columns[-1]
    summarize(
        "CWRU Bearing Fault (Case Western Reserve Univ.)",
        df,
        origin="CWRU bearing test-rig laboratory data (public benchmark). "
               "LABORATORY vibration measurements — not field measurements, "
               "but real measured accelerations. 9 time-domain features "
               "(max/min/mean/sd/rms/skewness/kurtosis/crest/form) + fault label.",
        task="Classification — bearing fault type "
             "(0=Normal / 1=Inner-Race / 2=Outer-Race / 3=Ball).",
        units={"features": "time-domain stats of 12.8 kHz DE/FE acceleration"},
        label_col=label,
    )


# ---------------------------------------------------------------------------
# 3) Pump Sensor — archive (2).zip
# ---------------------------------------------------------------------------
def analyze_pump() -> None:
    csv = RAW / "pump" / "sensor.csv"
    df = pd.read_csv(csv)
    label = "machine_status" if "machine_status" in df.columns else None
    summarize(
        "Pump Sensor Data",
        df,
        origin="Real industrial pump sensor log (public Kaggle dataset). "
               "FIELD-like time-series measurements from a water pump with "
               "documented breakdown events.",
        task="Time-series forecasting (LSTM) on a sensor channel AND "
             "anomaly detection against machine_status (NORMAL/BROKEN/RECOVERING).",
        units={"sensor_00..51": "raw sensor readings", "timestamp": "ISO datetime"},
        label_col=label,
    )
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], errors="coerce")
        line(f"- **Time span**: {ts.min()} → {ts.max()}  "
             f"({(ts.max()-ts.min()).days} days)")


# ---------------------------------------------------------------------------
# 4) ESP features — features.csv
# ---------------------------------------------------------------------------
def analyze_esp() -> None:
    df = pd.read_csv(RAW / "esp" / "features.csv", sep=";")
    summarize(
        "ESP Features (vibration-derived, ESPset)",
        df,
        origin="Features extracted from ESP (Electrical Submersible Pump) "
               "vibration signals. 11 ESPs labelled with real fault classes.",
        task="Multi-class classification — ESP fault type "
             "(Normal / Unbalance / Faulty sensor / Rubbing / Misalignment).",
        units={"features": "vibration statistical features (rms, median, peak, fit coeffs)"},
        label_col="label",
    )
    line(f"- **ESPs (esp_id)**: {sorted(df['esp_id'].unique())}")


# ---------------------------------------------------------------------------
# 5) Sorush field — xlsx + paper
# ---------------------------------------------------------------------------
def analyze_sorush() -> None:
    xlsx = RAW / "sorush" / "sorush_field.xlsx"
    df = pd.read_excel(xlsx, sheet_name="SorushField", header=2)
    # keep only the input/output columns (drop the metadata columns G/H/I/J)
    keep = ["Sample #", "Well", "D (1/64in)", "Pwh", "γo", "GLR", "QL"]
    df = df[[c for c in keep if c in df.columns]].copy()
    df.columns = ["sample", "well", "choke_d64", "pwh_psig", "oil_gravity",
                  "glr_scf_stb", "ql_stb_d"]
    summarize(
        "Sorush Oil Field (wellhead choke two-phase flow)",
        df,
        origin="Sorush oil field multi-well production records (7245 samples). "
               "Published supplementary data to Barjouei et al. 2021 "
               "(J. Pet. Explor. Prod. Technol.). REAL FIELD production data.",
        task="Regression — predict liquid flow rate QL (STB/D) from choke size, "
             "wellhead pressure, oil gravity and GLR.",
        units={"choke_d64": "1/64 in", "pwh_psig": "psig",
               "oil_gravity": "dimensionless", "glr_scf_stb": "scf/STB",
               "ql_stb_d": "STB/D"},
        label_col="well",
    )
    line(f"- **Wells**: {df['well'].nunique()} unique  |  "
         f"QL range: [{df['ql_stb_d'].min():.0f}, {df['ql_stb_d'].max():.0f}] STB/D")


def main() -> None:
    line("# Phase 2 — Dataset Quality & Suitability Report")
    line("Each dataset is analyzed independently. No merging is performed.")
    for fn in (analyze_cmapss, analyze_cwru, analyze_pump, analyze_esp, analyze_sorush):
        try:
            fn()
        except Exception as e:
            section(f"ERROR analyzing {fn.__name__}")
            line(f"```\n{type(e).__name__}: {e}\n```")
    out = OUT / "phase2_data_report.md"
    out.write_text("\n".join(REPORT_LINES), encoding="utf-8")
    print(f"\n[written] {out}")


if __name__ == "__main__":
    main()
