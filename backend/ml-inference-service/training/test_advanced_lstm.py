"""
Focused test suite for the fixed AdvancedLSTMModel.

Covers the six defects and the test list requested in the DOF task:
  1. Single-step training (horizon=1, 1D and 2D targets)
  2. Multi-step training (horizon>1, 2D target shape (n, horizon))
  3. 3D target handling (n, horizon, n_targets)
  4. External validation data (X_val/y_val) -- the original uninitialized-variable bug
  5. Attention model construction + training, with softmax-across-time verification
  6. Prediction output dimensions (forecast_steps <= horizon and > horizon)
  7. Model saving and loading round-trip
  8. Persistence baseline comparison (LSTM must not be worse than y_{t-1})

Run:
  cd /home/z/my-project/dof-repo/backend/ml-inference-service
  TF_CPP_MIN_LOG_LEVEL=3 TF_ENABLE_ONEDNN_OPTS=0 \
    python3 backend/ml-inference-service/training/test_advanced_lstm.py
"""

import json
import os
import sys
import tempfile

# Make the ml-inference-service package importable.
SVC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SVC_DIR)

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np
import tensorflow as tf

import advanced_lstm_model as lstm_mod

RESULTS = []


def record(name, passed, detail="", metrics=None):
    RESULTS.append(
        {
            "test": name,
            "passed": bool(passed),
            "detail": detail,
            "metrics": metrics or {},
        }
    )
    flag = "PASS" if passed else "FAIL"
    print(f"[{flag}] {name}: {detail}")


def make_series(n_points=600, seed=42):
    """Deterministic synthetic oil-well-like series: trend + seasonality + noise."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_points)
    data = (
        0.02 * t
        + 10.0 * np.sin(2 * np.pi * t / 50.0)
        + 4.0 * np.sin(2 * np.pi * t / 13.0)
        + rng.normal(0, 0.5, n_points)
    )
    return data.reshape(-1, 1).astype("float32")


def make_sequences(data, seq_len, horizon):
    X, y = [], []
    for i in range(len(data) - seq_len - horizon + 1):
        X.append(data[i : i + seq_len])
        y.append(data[i + seq_len : i + seq_len + horizon, 0])
    return np.array(X, dtype="float32"), np.array(y, dtype="float32")


# --------------------------------------------------------------------------- #
# Test 1: single-step training
# --------------------------------------------------------------------------- #
def test_single_step():
    data = make_series(500)
    X, y = make_sequences(data, seq_len=20, horizon=1)
    # y is currently 2D (n,1); also exercise the 1D path.
    y_1d = y[:, 0]
    model = lstm_mod.AdvancedLSTMModel(
        sequence_length=20, forecast_horizon=1, n_features=1, model_type="stacked_lstm"
    )
    metrics = model.train(
        X_train=X, y_train=y_1d, epochs=15, batch_size=32, validation_split=0.2, verbose=0
    )
    ok = (
        model.is_trained
        and metrics["epochs_trained"] >= 1
        and "checkpoint_path" in metrics
        and os.path.exists(metrics["checkpoint_path"])
        and metrics["train_loss"] is not None
    )
    record(
        "single_step_training",
        ok,
        f"epochs={metrics['epochs_trained']}, train_loss={metrics['train_loss']:.4f}, "
        f"ckpt={'exists' if os.path.exists(metrics.get('checkpoint_path','')) else 'MISSING'}",
        metrics,
    )
    return model, X, y


# --------------------------------------------------------------------------- #
# Test 2: multi-step training (2D target)
# --------------------------------------------------------------------------- #
def test_multi_step():
    data = make_series(600)
    seq_len, horizon = 24, 4
    X, y = make_sequences(data, seq_len, horizon)
    model = lstm_mod.AdvancedLSTMModel(
        sequence_length=seq_len, forecast_horizon=horizon, n_features=1,
        model_type="stacked_lstm",
    )
    metrics = model.train(
        X_train=X, y_train=y, epochs=15, batch_size=32, validation_split=0.2, verbose=0
    )
    ok = (
        model.is_trained
        and model.output_dim == horizon
        and model.model.output_shape[-1] == horizon
    )
    record(
        "multi_step_training",
        ok,
        f"output_dim={model.output_dim}, head_output={model.model.output_shape[-1]}, "
        f"val_loss={metrics['val_loss']}",
        metrics,
    )
    return model, X, y


# --------------------------------------------------------------------------- #
# Test 3: 3D target handling
# --------------------------------------------------------------------------- #
def test_3d_target():
    data = make_series(600)
    seq_len, horizon, n_targets = 20, 3, 2
    X, y2d = make_sequences(data, seq_len, horizon)
    # Construct a 3D target by stacking the series and a lagged copy as 2 channels.
    y3d = np.stack([y2d, np.roll(y2d, 1, axis=0)], axis=-1).astype("float32")
    model = lstm_mod.AdvancedLSTMModel(
        sequence_length=seq_len, forecast_horizon=horizon, n_features=1,
        model_type="stacked_lstm",
    )
    metrics = model.train(
        X_train=X, y_train=y3d, epochs=10, batch_size=32, validation_split=0.2, verbose=0
    )
    ok = (
        model.is_trained
        and model.n_targets == n_targets
        and model.output_dim == horizon * n_targets
        and model.model.output_shape[-1] == horizon * n_targets
    )
    record(
        "three_dim_target",
        ok,
        f"n_targets={model.n_targets}, output_dim={model.output_dim}, "
        f"head={model.model.output_shape[-1]}",
        metrics,
    )


# --------------------------------------------------------------------------- #
# Test 4: external validation data (the original NameError / shape bug)
# --------------------------------------------------------------------------- #
def test_external_validation():
    data = make_series(700)
    seq_len, horizon = 24, 3
    X, y = make_sequences(data, seq_len, horizon)
    split = int(len(X) * 0.8)
    X_tr, X_va = X[:split], X[split:]
    y_tr, y_va = y[:split], y[split:]
    # Pass X_val as 2D to exercise the reshape-before-allocate fix.
    X_val_2d = X_va.reshape(X_va.shape[0], -1)
    model = lstm_mod.AdvancedLSTMModel(
        sequence_length=seq_len, forecast_horizon=horizon, n_features=1,
        model_type="stacked_lstm",
    )
    try:
        metrics = model.train(
            X_train=X_tr, y_train=y_tr, X_val=X_val_2d, y_val=y_va,
            epochs=10, batch_size=32, verbose=0,
        )
        ok = (
            model.is_trained
            and metrics["val_loss"] is not None
            and metrics["train_loss"] is not None
            and metrics["epochs_trained"] >= 1
        )
        detail = (
            f"train_loss={metrics['train_loss']:.4f}, val_loss={metrics['val_loss']:.4f}, "
            f"epochs={metrics['epochs_trained']}"
        )
    except Exception as exc:  # noqa: BLE001 - we want to capture any failure
        ok = False
        detail = f"raised {type(exc).__name__}: {exc}"
        metrics = {}
    record("external_validation_data", ok, detail, metrics)


# --------------------------------------------------------------------------- #
# Test 5: attention softmax across the TIME axis
# --------------------------------------------------------------------------- #
def test_attention_softmax_axis():
    seq_len, n_features = 20, 1
    model = lstm_mod.AdvancedLSTMModel(
        sequence_length=seq_len, forecast_horizon=4, n_features=n_features,
        model_type="attention",
    )
    model.output_dim = 4
    net = model.build_model((seq_len, n_features))
    # Build a sub-model that exposes the attention_weights layer output.
    weights_layer = net.get_layer("attention_weights")
    sub = tf.keras.Model(net.inputs, [net.output, weights_layer.output])
    dummy = np.random.rand(5, seq_len, n_features).astype("float32")
    _, attn = sub.predict(dummy, verbose=0)  # attn shape: (5, seq_len, 1)
    # Softmax across time => weights for each sample sum to ~1.0 over the time axis.
    sums = attn.reshape(5, seq_len).sum(axis=1)
    all_one = np.allclose(sums, 1.0, atol=1e-5)
    not_uniform = not np.allclose(attn, attn[0, 0, 0])  # not all-equal (would be the bug)
    ok = bool(all_one and not_uniform)
    record(
        "attention_softmax_time_axis",
        ok,
        f"sums_over_time={np.round(sums,4).tolist()}, "
        f"weights_min={float(attn.min()):.4f}, weights_max={float(attn.max()):.4f}",
        {
            "sums_over_time": sums.tolist(),
            "weights_min": float(attn.min()),
            "weights_max": float(attn.max()),
        },
    )
    return model


def test_attention_training():
    data = make_series(500)
    seq_len, horizon = 20, 3
    X, y = make_sequences(data, seq_len, horizon)
    model = lstm_mod.AdvancedLSTMModel(
        sequence_length=seq_len, forecast_horizon=horizon, n_features=1,
        model_type="attention",
    )
    metrics = model.train(
        X_train=X, y_train=y, epochs=10, batch_size=32, validation_split=0.2, verbose=0
    )
    ok = model.is_trained and metrics["epochs_trained"] >= 1
    record(
        "attention_training",
        ok,
        f"epochs={metrics['epochs_trained']}, train_loss={metrics['train_loss']:.4f}",
        metrics,
    )
    return model, X, y


# --------------------------------------------------------------------------- #
# Test 6: prediction output dimensions
# --------------------------------------------------------------------------- #
def test_prediction_dims(model, X, horizon):
    hist = X[-1, :, 0]  # 1D history of length seq_len
    # Case A: forecast_steps <= horizon
    res_le = model.predict(hist, forecast_steps=horizon - 1)
    # Case B: forecast_steps == horizon
    res_eq = model.predict(hist, forecast_steps=horizon)
    # Case C: forecast_steps > horizon (recursive path for univariate)
    res_gt = model.predict(hist, forecast_steps=horizon + 3)
    ok = (
        len(res_le["predictions"]) == horizon - 1
        and len(res_eq["predictions"]) == horizon
        and len(res_gt["predictions"]) == horizon + 3
        and len(res_gt["confidence_lower"]) == horizon + 3
        and len(res_gt["confidence_upper"]) == horizon + 3
        and res_gt["forecast_steps"] == horizon + 3
    )
    record(
        "prediction_output_dims",
        ok,
        f"len(<h)={len(res_le['predictions'])}, len(==h)={len(res_eq['predictions'])}, "
        f"len(>h)={len(res_gt['predictions'])}",
    )


# --------------------------------------------------------------------------- #
# Test 7: save / load round-trip
# --------------------------------------------------------------------------- #
def test_save_load(model, X):
    tmp = tempfile.mkdtemp(prefix="lstm_save_")
    path = os.path.join(tmp, "roundtrip.keras")
    model.save_model(path)
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    # Reload into a fresh instance and compare predictions.
    hist = X[-1, :, 0]
    pred_before = model.predict(hist, forecast_steps=3)["predictions"]
    reloaded = lstm_mod.AdvancedLSTMModel(
        sequence_length=model.sequence_length,
        forecast_horizon=model.forecast_horizon,
        n_features=model.n_features,
        model_type=model.model_type,
    )
    reloaded.load_model(path)
    pred_after = reloaded.predict(hist, forecast_steps=3)["predictions"]
    match = np.allclose(pred_before, pred_after, atol=1e-4)
    ok = exists and reloaded.is_trained and match
    record(
        "save_load_roundtrip",
        ok,
        f"file_size={os.path.getsize(path) if exists else 0}B, "
        f"pred_match={match}, before={np.round(pred_before,3).tolist()}",
    )


# --------------------------------------------------------------------------- #
# Test 8: persistence baseline comparison
# --------------------------------------------------------------------------- #
def test_persistence_baseline():
    data = make_series(800, seed=7)
    seq_len, horizon = 24, 4
    X, y = make_sequences(data, seq_len, horizon)
    split = int(len(X) * 0.8)
    X_tr, X_te = X[:split], X[split:]
    y_tr, y_te = y[:split], y[split:]
    model = lstm_mod.AdvancedLSTMModel(
        sequence_length=seq_len, forecast_horizon=horizon, n_features=1,
        model_type="stacked_lstm",
    )
    model.train(
        X_train=X_tr, y_train=y_tr, epochs=25, batch_size=32,
        validation_split=0.1, verbose=0,
    )
    # LSTM MAE over the test set (direct multi-step: one pass per test window).
    preds_scaled = []
    for i in range(len(X_te)):
        p = model.predict(X_te[i, :, 0], forecast_steps=horizon)["predictions"]
        preds_scaled.append(p)
    preds = np.array(preds_scaled)
    lstm_mae = float(np.mean(np.abs(preds - y_te)))
    # Persistence baseline: predict the last observed value for all horizon steps.
    persist = np.repeat(X_te[:, -1, 0], horizon).reshape(len(X_te), horizon)
    persist_mae = float(np.mean(np.abs(persist - y_te)))
    not_worse = lstm_mae <= persist_mae
    record(
        "persistence_baseline",
        not_worse,
        f"LSTM_MAE={lstm_mae:.4f}, persistence_MAE={persist_mae:.4f}, "
        f"delta={lstm_mae - persist_mae:+.4f} ({'LSTM better' if not_worse else 'LSTM WORSE'})",
        {"lstm_mae": lstm_mae, "persistence_mae": persist_mae},
    )


# --------------------------------------------------------------------------- #
def main():
    print("=" * 70)
    print("AdvancedLSTMModel focused test suite")
    print("=" * 70)

    m1, X1, y1 = test_single_step()
    m2, X2, y2 = test_multi_step()
    test_3d_target()
    test_external_validation()
    test_attention_softmax_axis()
    m_att, X_att, y_att = test_attention_training()
    test_prediction_dims(m2, X2, horizon=4)
    test_save_load(m2, X2)
    test_persistence_baseline()

    passed = sum(r["passed"] for r in RESULTS)
    total = len(RESULTS)
    print("=" * 70)
    print(f"SUMMARY: {passed}/{total} tests passed")
    print("=" * 70)

    out_path = os.environ.get("LSTM_RESULTS_OUT", "lstm_test_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump({"passed": passed, "total": total, "results": RESULTS}, fh, indent=2)
    print(f"results written to {out_path}")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
