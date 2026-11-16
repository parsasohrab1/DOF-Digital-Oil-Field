#!/usr/bin/env python3
"""
Utility script to train and register ML models for the OGIM inference service.

Usage:
    python scripts/train_models.py --model all
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure repository modules are importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "shared"))
sys.path.insert(0, str(ROOT / "backend" / "ml-inference-service"))

from config import settings  # type: ignore  # noqa: E402
from mlflow_integration import get_mlflow_manager  # type: ignore  # noqa: E402


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("train-models")


def train_models(model: str) -> None:
    """Train requested model(s) and register outputs."""
    manager = get_mlflow_manager(
        model_path=settings.MODEL_STORAGE_PATH,
        tracking_uri=settings.MLFLOW_TRACKING_URI,
    )

    if model in {"anomaly_detection", "all"}:
        logger.info("Training anomaly detection model...")
        manager.train_anomaly_detection_model()
        manager.load_model("anomaly-detection")

    if model in {"failure_prediction", "all"}:
        logger.info("Training failure prediction model...")
        manager.train_failure_prediction_model()
        manager.load_model("failure-prediction")

    if model in {"time_series_forecast", "all"}:
        logger.info("Training time series forecast model (LSTM)...")
        manager.train_time_series_model()
        manager.load_model("time-series-forecast")

    logger.info("Reloading registry models...")
    manager.load_registered_models()
    logger.info("Training completed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train OGIM ML inference models.")
    parser.add_argument(
        "--model",
        choices=["anomaly_detection", "failure_prediction", "time_series_forecast", "all"],
        default="all",
        help="Model to train (default: all).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    train_models(args.model)


if __name__ == "__main__":
    main()

