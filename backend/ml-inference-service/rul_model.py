"""
Remaining Useful Life (RUL) Prediction Model
Specialized ML models for oil field equipment RUL prediction
"""
import logging
import numpy as np
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import os
import sys

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from config import settings

logger = logging.getLogger(__name__)

try:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    import joblib

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available, RUL model will use mock implementation")

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers

    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    logger.warning("TensorFlow not available, RUL model will use simpler models")


class RULModel:
    """
    Remaining Useful Life prediction model for oil field equipment

    Equipment types:
    - Pumps
    - Valves
    - Compressors
    - Wellheads
    - Pipelines
    """

    def __init__(self, equipment_type: str):
        self.equipment_type = equipment_type
        self.model = None
        self.scaler = StandardScaler() if SKLEARN_AVAILABLE else None
        self.is_trained = False
        self.feature_names = []

    def _get_default_features(self) -> List[str]:
        """Get default feature names for equipment"""
        base_features = [
            "temperature",
            "pressure",
            "vibration",
            "flow_rate",
            "operating_hours",
            "maintenance_count",
            "failure_count",
        ]

        # Equipment-specific features
        if self.equipment_type == "pump":
            base_features.extend(["pump_speed", "efficiency", "bearing_temperature"])
        elif self.equipment_type == "valve":
            base_features.extend(["valve_position", "actuator_pressure", "leak_rate"])
        elif self.equipment_type == "compressor":
            base_features.extend(
                ["compression_ratio", "discharge_temperature", "oil_level"]
            )
        elif self.equipment_type == "wellhead":
            base_features.extend(["well_pressure", "production_rate", "choke_position"])

        return base_features

    def train(self, X: np.ndarray, y: np.ndarray, model_type: str = "random_forest"):
        """
        Train RUL model

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Target RUL values in hours (n_samples,)
            model_type: "random_forest", "gradient_boosting", or "neural_network"
        """
        if not SKLEARN_AVAILABLE and not TENSORFLOW_AVAILABLE:
            logger.error("No ML library available for RUL model training")
            return

        # Scale features
        if self.scaler:
            X_scaled = self.scaler.fit_transform(X)
        else:
            X_scaled = X

        if model_type == "random_forest" and SKLEARN_AVAILABLE:
            self.model = RandomForestRegressor(
                n_estimators=100,
                max_depth=20,
                min_samples_split=5,
                random_state=42,
                n_jobs=-1,
            )
            self.model.fit(X_scaled, y)
            logger.info(f"Trained Random Forest RUL model for {self.equipment_type}")

        elif model_type == "gradient_boosting" and SKLEARN_AVAILABLE:
            self.model = GradientBoostingRegressor(
                n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42
            )
            self.model.fit(X_scaled, y)
            logger.info(
                f"Trained Gradient Boosting RUL model for {self.equipment_type}"
            )

        elif model_type == "neural_network" and TENSORFLOW_AVAILABLE:
            self.model = keras.Sequential(
                [
                    layers.Dense(
                        64, activation="relu", input_shape=(X_scaled.shape[1],)
                    ),
                    layers.Dropout(0.2),
                    layers.Dense(32, activation="relu"),
                    layers.Dropout(0.2),
                    layers.Dense(16, activation="relu"),
                    layers.Dense(1),  # RUL prediction
                ]
            )
            self.model.compile(optimizer="adam", loss="mse", metrics=["mae"])
            self.model.fit(
                X_scaled, y, epochs=50, batch_size=32, verbose=0, validation_split=0.2
            )
            logger.info(f"Trained Neural Network RUL model for {self.equipment_type}")

        else:
            logger.warning(f"Model type {model_type} not available, using mock model")
            self.model = "mock"

        self.is_trained = True

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Predict RUL for equipment

        Args:
            features: Dictionary of feature values

        Returns:
            Dictionary with RUL prediction and confidence
        """
        if not self.is_trained:
            return {
                "rul_hours": None,
                "rul_days": None,
                "confidence": 0.0,
                "error": "Model not trained",
            }

        # Convert features to array
        feature_names = self._get_default_features()
        feature_vector = np.array([features.get(name, 0.0) for name in feature_names])

        if self.model == "mock":
            # Mock prediction based on operating hours
            operating_hours = features.get("operating_hours", 0)
            base_rul = 8760 - operating_hours  # 1 year - operating hours
            rul_hours = max(
                0, base_rul * (1.0 - features.get("failure_count", 0) * 0.1)
            )

            return {
                "rul_hours": rul_hours,
                "rul_days": rul_hours / 24,
                "confidence": 0.7,
                "method": "mock",
            }

        # Scale features
        if self.scaler:
            feature_vector = self.scaler.transform(feature_vector.reshape(1, -1))
        else:
            feature_vector = feature_vector.reshape(1, -1)

        # Predict
        if TENSORFLOW_AVAILABLE and isinstance(self.model, keras.Model):
            rul_prediction = self.model.predict(feature_vector, verbose=0)[0][0]
        elif SKLEARN_AVAILABLE:
            rul_prediction = self.model.predict(feature_vector)[0]
        else:
            rul_prediction = 0

        # Calculate confidence based on feature completeness
        feature_completeness = sum(
            1 for name in feature_names if name in features
        ) / len(feature_names)
        confidence = min(0.95, 0.5 + feature_completeness * 0.45)

        return {
            "rul_hours": max(0, float(rul_prediction)),
            "rul_days": max(0, float(rul_prediction) / 24),
            "confidence": confidence,
            "equipment_type": self.equipment_type,
            "prediction_timestamp": datetime.utcnow().isoformat(),
        }

    def predict_batch(
        self, features_list: List[Dict[str, float]]
    ) -> List[Dict[str, Any]]:
        """Predict RUL for multiple equipment instances"""
        return [self.predict(features) for features in features_list]


class RULModelManager:
    """
    Manager for multiple RUL models for different equipment types
    """

    def __init__(self):
        self.models: Dict[str, RULModel] = {}
        self.model_path = settings.MODEL_STORAGE_PATH

    def get_model(self, equipment_type: str) -> RULModel:
        """Get or create RUL model for equipment type"""
        if equipment_type not in self.models:
            self.models[equipment_type] = RULModel(equipment_type)
        return self.models[equipment_type]

    def train_model(
        self,
        equipment_type: str,
        X: np.ndarray,
        y: np.ndarray,
        model_type: str = "random_forest",
    ):
        """Train RUL model for equipment type"""
        model = self.get_model(equipment_type)
        model.train(X, y, model_type)

        # Save model
        if self.model_path:
            os.makedirs(self.model_path, exist_ok=True)
            model_file = os.path.join(self.model_path, f"rul_{equipment_type}.pkl")
            if SKLEARN_AVAILABLE and hasattr(model.model, "predict"):
                joblib.dump(model.model, model_file)
                if model.scaler:
                    scaler_file = os.path.join(
                        self.model_path, f"rul_{equipment_type}_scaler.pkl"
                    )
                    joblib.dump(model.scaler, scaler_file)
                logger.info(f"Saved RUL model for {equipment_type} to {model_file}")

    def predict_rul(
        self, equipment_type: str, equipment_id: str, features: Dict[str, float]
    ) -> Dict[str, Any]:
        """Predict RUL for specific equipment"""
        model = self.get_model(equipment_type)
        prediction = model.predict(features)
        prediction["equipment_id"] = equipment_id
        return prediction

    def get_maintenance_recommendation(
        self, equipment_type: str, equipment_id: str, features: Dict[str, float]
    ) -> Dict[str, Any]:
        """Get maintenance recommendation based on RUL prediction"""
        rul_prediction = self.predict_rul(equipment_type, equipment_id, features)

        rul_days = rul_prediction.get("rul_days", 0)

        # Determine maintenance urgency
        if rul_days < 7:
            urgency = "critical"
            recommendation = "Immediate maintenance required"
        elif rul_days < 30:
            urgency = "high"
            recommendation = "Schedule maintenance within 1 week"
        elif rul_days < 90:
            urgency = "medium"
            recommendation = "Schedule maintenance within 1 month"
        else:
            urgency = "low"
            recommendation = "Routine maintenance sufficient"

        return {
            **rul_prediction,
            "urgency": urgency,
            "recommendation": recommendation,
            "maintenance_window_days": max(0, rul_days - 7),  # 7 days buffer
        }


# Global instance
rul_model_manager = RULModelManager()
