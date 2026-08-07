"""
Advanced LSTM Model for Oil Well Behavior Prediction
پیشرفته‌ترین مدل LSTM برای پیش‌بینی رفتار چاه نفتی
"""
import logging
import os
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras.models import Sequential, Model
    from tensorflow.keras.layers import (
        LSTM,
        Dense,
        Dropout,
        Input,
        Bidirectional,
        Concatenate,
        BatchNormalization,
        TimeDistributed,
        Multiply,
        Lambda,
    )
    from tensorflow.keras.optimizers import Adam
    from tensorflow.keras.callbacks import (
        EarlyStopping,
        ReduceLROnPlateau,
        ModelCheckpoint,
    )
    from sklearn.preprocessing import MinMaxScaler, StandardScaler

    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    logger.warning("TensorFlow not available. Advanced LSTM models will not work.")

logger = logging.getLogger(__name__)


class AdvancedLSTMModel:
    """
    Advanced LSTM model for oil well time series prediction
    با معماری پیشرفته برای پیش‌بینی دقیق‌تر رفتار چاه
    """

    def __init__(
        self,
        sequence_length: int = 60,
        forecast_horizon: int = 24,  # پیش‌بینی 24 ساعت آینده
        n_features: int = 1,
        model_type: str = "stacked_lstm",  # stacked_lstm, bidirectional, attention
    ):
        self.sequence_length = sequence_length
        self.forecast_horizon = forecast_horizon
        self.n_features = n_features
        self.model_type = model_type
        self.model: Optional[Model] = None
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.feature_scalers: Dict[int, MinMaxScaler] = {}
        self.is_trained = False
        self.training_history: Dict[str, List[float]] = {}

    def _create_sequences(
        self, data: np.ndarray, seq_length: int, forecast_horizon: int = 1
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create sequences for LSTM training
        ایجاد دنباله‌ها برای آموزش LSTM
        """
        X, y = [], []
        for i in range(len(data) - seq_length - forecast_horizon + 1):
            X.append(data[i : (i + seq_length)])
            y.append(data[i + seq_length : i + seq_length + forecast_horizon])
        return np.array(X), np.array(y)

    def _build_stacked_lstm_model(self, input_shape: Tuple[int, int]) -> Model:
        """Build stacked LSTM model with multiple layers"""
        model = Sequential(
            [
                # First LSTM layer
                LSTM(128, return_sequences=True, input_shape=input_shape),
                BatchNormalization(),
                Dropout(0.3),
                # Second LSTM layer
                LSTM(64, return_sequences=True),
                BatchNormalization(),
                Dropout(0.3),
                # Third LSTM layer
                LSTM(32, return_sequences=False),
                BatchNormalization(),
                Dropout(0.2),
                # Dense layers
                Dense(64, activation="relu"),
                Dropout(0.2),
                Dense(32, activation="relu"),
                Dense(self.forecast_horizon),
            ]
        )
        return model

    def _build_bidirectional_lstm_model(self, input_shape: Tuple[int, int]) -> Model:
        """Build bidirectional LSTM model"""
        model = Sequential(
            [
                Bidirectional(
                    LSTM(128, return_sequences=True), input_shape=input_shape
                ),
                BatchNormalization(),
                Dropout(0.3),
                Bidirectional(LSTM(64, return_sequences=True)),
                BatchNormalization(),
                Dropout(0.3),
                Bidirectional(LSTM(32, return_sequences=False)),
                BatchNormalization(),
                Dropout(0.2),
                Dense(64, activation="relu"),
                Dropout(0.2),
                Dense(32, activation="relu"),
                Dense(self.forecast_horizon),
            ]
        )
        return model

    def _build_attention_lstm_model(self, input_shape: Tuple[int, int]) -> Model:
        """Build LSTM model with attention mechanism"""
        inputs = Input(shape=input_shape)

        # LSTM layers
        lstm1 = LSTM(128, return_sequences=True)(inputs)
        lstm1 = BatchNormalization()(lstm1)
        lstm1 = Dropout(0.3)(lstm1)

        lstm2 = LSTM(64, return_sequences=True)(lstm1)
        lstm2 = BatchNormalization()(lstm2)
        lstm2 = Dropout(0.3)(lstm2)

        # Attention mechanism (simplified self-attention)
        # Compute attention scores
        attention_scores = Dense(64, activation="tanh")(lstm2)
        attention_scores = Dense(1, activation="softmax", name="attention_weights")(
            attention_scores
        )

        # Apply attention
        attention_output = Multiply()([lstm2, attention_scores])
        attention_output = Lambda(lambda x: tf.reduce_sum(x, axis=1))(attention_output)

        # Dense layers
        dense1 = Dense(64, activation="relu")(attention_output)
        dense1 = Dropout(0.2)(dense1)
        dense2 = Dense(32, activation="relu")(dense1)
        outputs = Dense(self.forecast_horizon)(dense2)

        model = Model(inputs=inputs, outputs=outputs)
        return model

    def build_model(self, input_shape: Tuple[int, int]) -> Model:
        """Build the selected model architecture"""
        if self.model_type == "stacked_lstm":
            model = self._build_stacked_lstm_model(input_shape)
        elif self.model_type == "bidirectional":
            model = self._build_bidirectional_lstm_model(input_shape)
        elif self.model_type == "attention":
            model = self._build_attention_lstm_model(input_shape)
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")

        # Compile model with advanced optimizer
        optimizer = Adam(learning_rate=0.001, beta_1=0.9, beta_2=0.999)
        model.compile(optimizer=optimizer, loss="mse", metrics=["mae", "mape"])

        return model

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        epochs: int = 100,
        batch_size: int = 32,
        validation_split: float = 0.2,
        verbose: int = 1,
    ) -> Dict[str, Any]:
        """
        Train the advanced LSTM model
        آموزش مدل LSTM پیشرفته
        """
        if not TENSORFLOW_AVAILABLE:
            raise RuntimeError("TensorFlow is required for advanced LSTM models.")

        # Normalize data
        if X_train.ndim == 2:
            X_train = X_train.reshape(-1, X_train.shape[1], 1)
        if y_train.ndim == 1:
            y_train = y_train.reshape(-1, 1)

        # Scale features
        n_samples, n_timesteps, n_features = X_train.shape
        X_train_scaled = np.zeros_like(X_train)

        for i in range(n_features):
            feature_data = X_train[:, :, i].reshape(-1, 1)
            scaler = MinMaxScaler(feature_range=(0, 1))
            scaled_feature = scaler.fit_transform(feature_data)
            X_train_scaled[:, :, i] = scaled_feature.reshape(n_samples, n_timesteps)
            self.feature_scalers[i] = scaler

        # Scale target
        y_scaler = MinMaxScaler(feature_range=(0, 1))
        y_train_scaled = y_scaler.fit_transform(y_train)
        self.scaler = y_scaler

        # Build model
        input_shape = (self.sequence_length, n_features)
        self.model = self.build_model(input_shape)

        # Prepare validation data
        validation_data = None
        if X_val is not None and y_val is not None:
            # Scale validation data
            X_val_scaled = np.zeros_like(X_val)
            if X_val.ndim == 2:
                X_val = X_val.reshape(-1, X_val.shape[1], 1)

            for i in range(n_features):
                feature_data = X_val[:, :, i].reshape(-1, 1)
                scaled_feature = self.feature_scalers[i].transform(feature_data)
                X_val_scaled[:, :, i] = scaled_feature.reshape(
                    X_val.shape[0], self.sequence_length
                )

            y_val_scaled = y_scaler.transform(y_val.reshape(-1, 1))
            validation_data = (X_val_scaled, y_val_scaled)
        elif validation_split > 0:
            # Split training data
            split_idx = int(len(X_train_scaled) * (1 - validation_split))
            X_train_final = X_train_scaled[:split_idx]
            y_train_final = y_train_scaled[:split_idx]
            X_val_scaled = X_train_scaled[split_idx:]
            y_val_scaled = y_train_scaled[split_idx:]
            validation_data = (X_val_scaled, y_val_scaled)
        else:
            X_train_final = X_train_scaled
            y_train_final = y_train_scaled

        # Callbacks
        callbacks = [
            EarlyStopping(
                monitor="val_loss", patience=15, restore_best_weights=True, verbose=1
            ),
            ReduceLROnPlateau(
                monitor="val_loss", factor=0.5, patience=5, min_lr=1e-7, verbose=1
            ),
            ModelCheckpoint(
                filepath="best_lstm_model.h5",
                monitor="val_loss",
                save_best_only=True,
                verbose=1,
            ),
        ]

        # Train model
        history = self.model.fit(
            X_train_final,
            y_train_final,
            epochs=epochs,
            batch_size=batch_size,
            validation_data=validation_data,
            callbacks=callbacks,
            verbose=verbose,
        )

        self.training_history = {
            "loss": history.history["loss"],
            "val_loss": history.history.get("val_loss", []),
            "mae": history.history.get("mae", []),
            "val_mae": history.history.get("val_mae", []),
        }

        self.is_trained = True

        # Evaluate
        if validation_data:
            val_loss, val_mae, val_mape = self.model.evaluate(
                validation_data[0], validation_data[1], verbose=0
            )
        else:
            val_loss, val_mae, val_mape = None, None, None

        train_loss, train_mae, train_mape = self.model.evaluate(
            X_train_final, y_train_final, verbose=0
        )

        return {
            "train_loss": float(train_loss),
            "train_mae": float(train_mae),
            "train_mape": float(train_mape),
            "val_loss": float(val_loss) if val_loss else None,
            "val_mae": float(val_mae) if val_mae else None,
            "val_mape": float(val_mape) if val_mape else None,
            "epochs_trained": len(history.history["loss"]),
        }

    def predict(
        self, historical_data: np.ndarray, forecast_steps: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Predict future values
        پیش‌بینی مقادیر آینده
        """
        if not self.is_trained or self.model is None:
            raise RuntimeError("Model must be trained before prediction.")

        if forecast_steps is None:
            forecast_steps = self.forecast_horizon

        # Prepare input
        if historical_data.ndim == 1:
            historical_data = historical_data.reshape(-1, 1)

        if len(historical_data) < self.sequence_length:
            raise ValueError(
                f"Historical data must have at least {self.sequence_length} points, "
                f"got {len(historical_data)}"
            )

        # Use last sequence_length points
        input_data = historical_data[-self.sequence_length :]

        # Scale input
        n_features = input_data.shape[1] if input_data.ndim > 1 else 1
        input_scaled = np.zeros((1, self.sequence_length, n_features))

        for i in range(n_features):
            feature_data = input_data[:, i].reshape(-1, 1)
            if i in self.feature_scalers:
                scaled_feature = self.feature_scalers[i].transform(feature_data)
            else:
                # Use target scaler as fallback
                scaled_feature = self.scaler.transform(feature_data)
            input_scaled[0, :, i] = scaled_feature.flatten()

        # Predict
        predictions_scaled = []
        current_sequence = input_scaled.copy()

        for step in range(forecast_steps):
            # Predict next step
            pred = self.model.predict(current_sequence, verbose=0)
            predictions_scaled.append(pred[0, 0])

            # Update sequence for next prediction (rolling window)
            if step < forecast_steps - 1:
                # Shift sequence and add prediction
                current_sequence = np.roll(current_sequence, -1, axis=1)
                current_sequence[0, -1, 0] = pred[0, 0]

        # Inverse transform predictions
        predictions_array = np.array(predictions_scaled).reshape(-1, 1)
        predictions_original = self.scaler.inverse_transform(predictions_array)
        predictions_original = predictions_original.flatten().tolist()

        # Calculate confidence intervals (simplified)
        # In production, use proper prediction intervals
        std_dev = np.std(predictions_array)
        confidence_lower = [p - 1.96 * std_dev for p in predictions_original]
        confidence_upper = [p + 1.96 * std_dev for p in predictions_original]

        return {
            "predictions": predictions_original,
            "confidence_lower": confidence_lower,
            "confidence_upper": confidence_upper,
            "forecast_steps": forecast_steps,
            "sequence_length": self.sequence_length,
            "confidence": 0.90,  # 90% confidence interval
            "model_type": self.model_type,
        }

    def save_model(self, filepath: str):
        """Save model to file"""
        if self.model is None:
            raise RuntimeError("No model to save.")

        self.model.save(filepath)
        logger.info(f"Model saved to {filepath}")

    def load_model(self, filepath: str):
        """Load model from file"""
        if not TENSORFLOW_AVAILABLE:
            raise RuntimeError("TensorFlow is required to load models.")

        self.model = keras.models.load_model(filepath)
        self.is_trained = True
        logger.info(f"Model loaded from {filepath}")


# Global instance for well-specific models
_well_models: Dict[str, AdvancedLSTMModel] = {}


def get_well_model(
    well_name: str, model_type: str = "stacked_lstm"
) -> AdvancedLSTMModel:
    """Get or create LSTM model for a specific well"""
    key = f"{well_name}_{model_type}"
    if key not in _well_models:
        _well_models[key] = AdvancedLSTMModel(
            sequence_length=60, forecast_horizon=24, n_features=1, model_type=model_type
        )
    return _well_models[key]
