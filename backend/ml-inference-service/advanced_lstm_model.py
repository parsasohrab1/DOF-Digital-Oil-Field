"""
Advanced LSTM Model for Oil Well Behavior Prediction
پیشرفته‌ترین مدل LSTM برای پیش‌بینی رفتار چاه نفتی

Fixes applied (see backend/ml-inference-service/ML_DEVELOPMENT_REPORT.md §2):
  1. 2D/3D target handling (n_targets / output_dim instead of hardcoded horizon head).
  2. Multi-step inverse scaling done in output_dim-wide chunks (single call).
  3. External validation data: reshape-before-allocate, no uninitialized
     X_train_final/y_train_final, y_val normalized like y_train.
  4. Attention softmax applied across the TIME axis (not a size-1 trailing axis).
  5. Direct multi-step prediction; recursive rolling only for the univariate
     single-target case, otherwise an explicit NotImplementedError.
  6. Deterministic ModelCheckpoint path under models/lstm/ (module-relative),
     monitor falls back to "loss" when no validation data is available.
  + save/load round-trip now persists the fitted scalers via a .meta.pkl sidecar.
"""

import logging
import os
import pickle
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

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
        # Fix 1: target geometry (set during train(), used by build_model)
        self.n_targets: int = 1
        self.output_dim: int = forecast_horizon

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
                Dense(self.output_dim),  # Fix 1: horizon * n_targets
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
                Dense(self.output_dim),  # Fix 1: horizon * n_targets
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
        # Fix 4: per-timestep linear scores, then softmax ACROSS THE TIME AXIS.
        # The previous Dense(1, activation="softmax") softmaxed a trailing axis
        # of size 1, giving every weight exactly 1.0 (attention disabled).
        attention_scores = Dense(64, activation="tanh")(lstm2)
        attention_scores = Dense(1, name="attention_scores")(attention_scores)
        attention_weights = Lambda(
            lambda x: tf.nn.softmax(x, axis=1), name="attention_weights"
        )(attention_scores)

        # Apply attention
        attention_output = Multiply()([lstm2, attention_weights])
        attention_output = Lambda(lambda x: tf.reduce_sum(x, axis=1))(attention_output)

        # Dense layers
        dense1 = Dense(64, activation="relu")(attention_output)
        dense1 = Dropout(0.2)(dense1)
        dense2 = Dense(32, activation="relu")(dense1)
        outputs = Dense(self.output_dim)(dense2)  # Fix 1

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

    def _normalize_target(self, y: np.ndarray) -> Tuple[np.ndarray, int]:
        """Fix 1: normalize 1D/2D/3D targets to 2D (n, output_dim) and set geometry."""
        if y.ndim == 1:
            y = y.reshape(-1, 1)
            self.n_targets = 1
        elif y.ndim == 2:
            self.n_targets = 1
        elif y.ndim == 3:
            # (n, horizon, n_targets) -> (n, horizon * n_targets)
            n, h, t = y.shape
            if h != self.forecast_horizon:
                raise ValueError(
                    f"y axis 1 ({h}) does not match forecast_horizon "
                    f"({self.forecast_horizon})"
                )
            y = y.reshape(n, h * t)
            self.n_targets = t
        else:
            raise ValueError(f"Unsupported y_train shape {y.shape}")
        self.output_dim = self.forecast_horizon * self.n_targets
        return y

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

        # Fix 1: normalize target geometry (1D/2D/3D) and compute output_dim
        y_train = self._normalize_target(np.asarray(y_train))

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
        # Fix 3: X_train_final/y_train_final must ALWAYS be defined (the
        # original code left them undefined when X_val was supplied, causing a
        # NameError at the final evaluate() call).
        X_train_final = X_train_scaled
        y_train_final = y_train_scaled

        if X_val is not None and y_val is not None:
            # Fix 3: reshape BEFORE allocating the scaled buffer (the original
            # allocated np.zeros_like(X_val) with the wrong 2D shape, then
            # silently mis-assigned into it).
            X_val = np.asarray(X_val)
            if X_val.ndim == 2:
                X_val = X_val.reshape(-1, self.sequence_length, 1)
            if X_val.shape[1:] != (self.sequence_length, n_features):
                raise ValueError(
                    f"X_val shape {X_val.shape} incompatible with training "
                    f"input ({self.sequence_length}, {n_features})"
                )
            X_val_scaled = np.zeros_like(X_val)
            for i in range(n_features):
                feature_data = X_val[:, :, i].reshape(-1, 1)
                scaled_feature = self.feature_scalers[i].transform(feature_data)
                X_val_scaled[:, :, i] = scaled_feature.reshape(
                    X_val.shape[0], self.sequence_length
                )

            # Fix 3: normalize y_val the same way as y_train (the original
            # reshape(-1, 1) scrambled multi-step targets).
            y_val = self._normalize_target(np.asarray(y_val))
            if y_val.shape[1] != self.output_dim:
                raise ValueError(
                    f"y_val has {y_val.shape[1]} columns, expected "
                    f"{self.output_dim} (horizon {self.forecast_horizon} x "
                    f"n_targets {self.n_targets})"
                )
            y_val_scaled = y_scaler.transform(y_val)
            validation_data = (X_val_scaled, y_val_scaled)
        elif validation_split > 0:
            # Split training data
            split_idx = int(len(X_train_scaled) * (1 - validation_split))
            X_train_final = X_train_scaled[:split_idx]
            y_train_final = y_train_scaled[:split_idx]
            X_val_scaled = X_train_scaled[split_idx:]
            y_val_scaled = y_train_scaled[split_idx:]
            validation_data = (X_val_scaled, y_val_scaled)

        # Callbacks
        # Fix 6: deterministic checkpoint path, module-relative models/lstm/
        # directory (the original used CWD-relative best_lstm_model.h5, which
        # collided across wells and depended on the working directory).
        ckpt_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "lstm")
        os.makedirs(ckpt_dir, exist_ok=True)
        ckpt_path = os.path.join(
            ckpt_dir,
            "{mt}_seq{sl}_h{fh}_f{nf}_t{nt}_best.keras".format(
                mt=self.model_type,
                sl=self.sequence_length,
                fh=self.forecast_horizon,
                nf=n_features,
                nt=self.n_targets,
            ),
        )
        monitor = "val_loss" if validation_data is not None else "loss"
        callbacks = [
            EarlyStopping(
                monitor=monitor, patience=15, restore_best_weights=True, verbose=1
            ),
            ReduceLROnPlateau(
                monitor=monitor, factor=0.5, patience=5, min_lr=1e-7, verbose=1
            ),
            ModelCheckpoint(
                filepath=ckpt_path,
                monitor=monitor,
                save_best_only=True,
                verbose=0,
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
            "val_loss": float(val_loss) if val_loss is not None else None,
            "val_mae": float(val_mae) if val_mae is not None else None,
            "val_mape": float(val_mape) if val_mape is not None else None,
            "epochs_trained": len(history.history["loss"]),
            "checkpoint_path": ckpt_path,  # Fix 6: reported, deterministic
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

        # Predict — Fix 5: the model head is DIRECT multi-step (one forward
        # pass produces all forecast_horizon*n_targets outputs). The original
        # looped one step at a time reading only pred[0, 0], mixing two
        # incompatible strategies and dropping the remaining outputs.
        horizon = self.forecast_horizon
        n_targets = self.n_targets
        univariate_single_target = (n_features == 1) and (n_targets == 1)

        if forecast_steps <= horizon:
            preds_scaled = self.model.predict(input_scaled, verbose=0)[0]
            preds_scaled = preds_scaled[: forecast_steps * n_targets]
        elif univariate_single_target:
            # Recursive rolling forecast for the univariate single-target case:
            # feed the predicted scaled values back into the window.
            preds_scaled = []
            current_sequence = input_scaled.copy()
            while len(preds_scaled) < forecast_steps:
                chunk = self.model.predict(current_sequence, verbose=0)[0]
                preds_scaled.extend(chunk.tolist())
                # Shift window and append the first predicted step
                current_sequence = np.roll(current_sequence, -1, axis=1)
                current_sequence[0, -1, 0] = chunk[0]
            preds_scaled = np.array(preds_scaled[:forecast_steps])
        else:
            raise NotImplementedError(
                f"Recursive forecasting beyond one horizon "
                f"(forecast_steps={forecast_steps} > horizon={horizon}) is not "
                f"supported for multi-feature or multi-target models."
            )

        # Fix 2: inverse-transform in output_dim-wide chunks so the scaler sees
        # the column count it was fit on (the original reshaped to (-1, 1) and
        # crashed or scrambled multi-step outputs).
        preds_scaled = np.asarray(preds_scaled, dtype="float32").flatten()
        n_rows = int(np.ceil(preds_scaled.size / self.output_dim))
        pad = n_rows * self.output_dim - preds_scaled.size
        if pad:
            preds_scaled = np.pad(preds_scaled, (0, pad))
        preds_scaled = preds_scaled.reshape(n_rows, self.output_dim)
        predictions_original = self.scaler.inverse_transform(preds_scaled)
        predictions_original = predictions_original.flatten()[:forecast_steps].tolist()

        # Calculate confidence intervals (simplified)
        # In production, use proper prediction intervals
        std_dev = float(np.std(preds_scaled))
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
        # Persist the fitted scalers + geometry so a load into a fresh
        # instance can predict without re-fitting (original load left
        # self.scaler / self.feature_scalers unfitted -> NotFittedError).
        meta = {
            "scaler": self.scaler,
            "feature_scalers": self.feature_scalers,
            "sequence_length": self.sequence_length,
            "forecast_horizon": self.forecast_horizon,
            "n_features": self.n_features,
            "n_targets": self.n_targets,
            "output_dim": self.output_dim,
            "model_type": self.model_type,
        }
        with open(filepath + ".meta.pkl", "wb") as fh:
            pickle.dump(meta, fh)
        logger.info(f"Model saved to {filepath}")

    def load_model(self, filepath: str):
        """Load model from file"""
        if not TENSORFLOW_AVAILABLE:
            raise RuntimeError("TensorFlow is required to load models.")

        self.model = keras.models.load_model(
            filepath,
            compile=False,
            custom_objects={
                "tf": tf,
            },
        )
        meta_path = filepath + ".meta.pkl"
        if os.path.exists(meta_path):
            with open(meta_path, "rb") as fh:
                meta = pickle.load(fh)
            self.scaler = meta["scaler"]
            self.feature_scalers = meta["feature_scalers"]
            self.sequence_length = meta["sequence_length"]
            self.forecast_horizon = meta["forecast_horizon"]
            self.n_features = meta["n_features"]
            self.n_targets = meta["n_targets"]
            self.output_dim = meta["output_dim"]
            self.model_type = meta["model_type"]
        else:
            # Best effort: infer geometry from the loaded graph so predict()
            # at least works for single-target models saved without a sidecar.
            self.output_dim = self.model.output_shape[-1]
            self.n_targets = 1
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
