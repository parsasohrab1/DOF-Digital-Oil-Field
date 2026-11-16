"""Shared helpers for DOF ML training scripts."""
import json
import os
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np

# CJK-safe fonts (no-op here but keeps plots portable)
for _f in ("/usr/share/fonts/truetype/chinese/NotoSansSC-Regular.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
    try:
        if os.path.exists(_f):
            fm.fontManager.addfont(_f)
    except Exception:
        pass
plt.rcParams["font.sans-serif"] = ["Noto Sans SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[1]  # .../ml
CLEANED = ROOT / "datasets" / "cleaned"
MODELS = ROOT / "models"
EVAL = ROOT / "evaluation"
RAW = ROOT / "datasets" / "raw"
MODELS.mkdir(parents=True, exist_ok=True)
EVAL.mkdir(parents=True, exist_ok=True)


def load_specs() -> dict:
    return json.loads((CLEANED / "feature_specs.json").read_text("utf-8"))


def save_metrics(name: str, metrics: dict) -> Path:
    metrics = {**metrics, "trained_at": datetime.utcnow().isoformat() + "Z"}
    p = EVAL / f"{name}_metrics.json"
    p.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    print(f"  [metrics] {p}")
    return p


def save_meta(name: str, meta: dict) -> Path:
    import joblib
    p = MODELS / f"{name}_meta.pkl"
    joblib.dump(meta, p)
    print(f"  [meta] {p}")
    return p


def save_plot(fig, name: str) -> Path:
    p = EVAL / f"{name}.png"
    fig.savefig(p, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  [plot] {p}")
    return p


def now() -> str:
    return datetime.utcnow().isoformat() + "Z"
