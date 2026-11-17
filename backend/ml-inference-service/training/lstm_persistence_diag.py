"""Diagnose why the LSTM underperforms persistence on a trending series.

Checks:
  1. Does longer training (60 epochs) close the gap?
  2. Does the LSTM beat persistence on the TRAIN split (sanity: did it learn)?
  3. Are test targets outside the training MinMax range (extrapolation failure)?
"""

import os
import sys

SVC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SVC_DIR)
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np
import advanced_lstm_model as lstm_mod


def make_series(n_points=800, seed=7):
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


def mae(a, b):
    return float(np.mean(np.abs(a - b)))


def main():
    data = make_series(800, seed=7)
    seq_len, horizon = 24, 4
    X, y = make_sequences(data, seq_len, horizon)
    split = int(len(X) * 0.8)
    X_tr, X_te = X[:split], X[split:]
    y_tr, y_te = y[:split], y[split:]

    print(f"series range: train y [{y_tr.min():.2f}, {y_tr.max():.2f}]; "
          f"test y [{y_te.min():.2f}, {y_te.max():.2f}]")
    frac_test_above_train_max = float(np.mean(y_te > y_tr.max()))
    frac_test_below_train_min = float(np.mean(y_te < y_tr.min()))
    print(f"test targets above train max: {frac_test_above_train_max:.1%}; "
          f"below train min: {frac_test_below_train_min:.1%}")

    model = lstm_mod.AdvancedLSTMModel(
        sequence_length=seq_len, forecast_horizon=horizon, n_features=1,
        model_type="stacked_lstm",
    )
    model.train(
        X_train=X_tr, y_train=y_tr, epochs=60, batch_size=32,
        validation_split=0.1, verbose=0,
    )

    # LSTM predictions on train and test.
    def predict_set(X_set):
        out = []
        for i in range(len(X_set)):
            p = model.predict(X_set[i, :, 0], forecast_steps=horizon)["predictions"]
            out.append(p)
        return np.array(out)

    pred_tr = predict_set(X_tr[-200:])  # last 200 train windows
    pred_te = predict_set(X_te)
    y_tr_eval = y_tr[-200:]
    lstm_mae_tr = mae(pred_tr, y_tr_eval)
    lstm_mae_te = mae(pred_te, y_te)

    persist_tr = np.repeat(X_tr[-200:, -1, 0], horizon).reshape(200, horizon)
    persist_te = np.repeat(X_te[:, -1, 0], horizon).reshape(len(X_te), horizon)
    persist_mae_tr = mae(persist_tr, y_tr_eval)
    persist_mae_te = mae(persist_te, y_te)

    print()
    print(f"TRAIN: LSTM_MAE={lstm_mae_tr:.4f}  persistence_MAE={persist_mae_tr:.4f}  "
          f"({'LSTM better' if lstm_mae_tr <= persist_mae_tr else 'LSTM WORSE'})")
    print(f"TEST : LSTM_MAE={lstm_mae_te:.4f}  persistence_MAE={persist_mae_te:.4f}  "
          f"({'LSTM better' if lstm_mae_te <= persist_mae_te else 'LSTM WORSE'})")
    print()
    print("sample test preds vs actuals (first 3 windows, 4 steps):")
    for i in range(3):
        print(f"  pred={np.round(pred_te[i],2).tolist()}  actual={np.round(y_te[i],2).tolist()}")

    out = {
        "train_lstm_mae": lstm_mae_tr,
        "train_persistence_mae": persist_mae_tr,
        "test_lstm_mae": lstm_mae_te,
        "test_persistence_mae": persist_mae_te,
        "frac_test_above_train_max": frac_test_above_train_max,
        "frac_test_below_train_min": frac_test_below_train_min,
    }
    os.makedirs("/home/z/my-project/work", exist_ok=True)
    with open("/home/z/my-project/work/lstm_persistence_diag.json", "w") as fh:
        import json
        json.dump(out, fh, indent=2)
    print(f"\ndiag written to /home/z/my-project/work/lstm_persistence_diag.json")


if __name__ == "__main__":
    main()
