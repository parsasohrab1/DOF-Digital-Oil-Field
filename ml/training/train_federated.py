"""
Phase 4g — Federated learning demonstration on real ESP data (binary).

Each of the 11 ESPs (esp_id 0..10) is an edge "node" holding its private
data. Task: predict Normal (0) vs Fault (1) — the standard federated
failure-detection framing, and the shape that matches the service's
FederatedLearningCoordinator (a single weight vector + bias).

Each node trains a LOCAL binary LogisticRegression; the coordinator
aggregates (coef, intercept) via data-size-weighted FedAvg (McMahan 2017) —
the SAME math as backend/ml-inference-service/federated_learning.py.

Leakage-safe: a global held-out test set (units unseen by any node) is used
to evaluate (a) per-node local accuracy, (b) FedAvg global accuracy over
multiple rounds, (c) a centralized upper-bound baseline. All metrics real.
Run:  python -I train_federated.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from common import CLEANED, EVAL, load_specs, save_metrics

def fedavg(nodes):
    """Data-size-weighted average of (coef[1,n], intercept[1]) over nodes."""
    total = sum(n["n"] for n in nodes)
    coef = sum(n["coef"] * (n["n"] / total) for n in nodes)
    inter = sum(n["intercept"] * (n["n"] / total) for n in nodes)
    return coef, inter

def main():
    specs = load_specs(); sp = specs["datasets"]["esp"]
    feat = sp["features"]
    print(f"Federated ESP (binary Normal-vs-Fault) — {len(feat)} features, 11 nodes")
    df = pd.read_csv(CLEANED / "esp_features_clean.csv")
    # Binary target: Normal(0) vs any fault(1)
    df["y"] = (df["label_id"] != 0).astype(int)
    # global held-out test (stratified), never seen by any node
    tr_idx, te_idx = train_test_split(np.arange(len(df)), test_size=0.2,
        random_state=42, stratify=df["y"])
    dtr, dte = df.iloc[tr_idx], df.iloc[te_idx]
    Xte = dte[feat].values; yte = dte["y"].values
    scaler = StandardScaler().fit(dtr[feat].values)
    Xte_s = scaler.transform(Xte)

    nodes = []
    for eid, sub in dtr.groupby("esp_id"):
        if sub["y"].nunique() < 2 or len(sub) < 20:
            continue  # node cannot train a binary classifier
        Xs = scaler.transform(sub[feat].values); ys = sub["y"].values
        m = LogisticRegression(max_iter=400, class_weight="balanced")
        m.fit(Xs, ys)
        nodes.append({"esp_id": int(eid), "n": int(len(sub)),
            "coef": m.coef_.copy(),      # shape (1, n_feat)
            "intercept": m.intercept_.copy(),  # shape (1,)
            "local_acc": float(accuracy_score(ys, m.predict(Xs))),
            "pos_rate": float(ys.mean())})
    print(f"  {len(nodes)} nodes trained locally "
          f"(avg local acc={np.mean([n['local_acc'] for n in nodes]):.3f})")

    # --- FedAvg round 1 ---
    g_coef, g_inter = fedavg(nodes)
    def global_predict(X):
        z = X @ g_coef.ravel() + g_inter[0]
        return (1 / (1 + np.exp(-z)) >= 0.5).astype(int)
    g1_acc = accuracy_score(yte, global_predict(Xte_s))
    g1_f1 = f1_score(yte, global_predict(Xte_s), zero_division=0)
    print(f"  FedAvg round 1: global_acc={g1_acc:.3f} F1={g1_f1:.3f}")

    # --- Iterative FedAvg rounds (warm-start each node from the global) ---
    round_history = [{"round": 1, "global_acc": float(g1_acc)}]
    for r in range(2, 6):
        rn = []
        for n in nodes:
            lr = LogisticRegression(max_iter=200, class_weight="balanced",
                warm_start=True)
            lr.coef_ = g_coef.copy(); lr.intercept_ = g_inter.copy()
            lr.classes_ = np.array([0, 1])
            sub = dtr[dtr["esp_id"] == n["esp_id"]]
            Xs = scaler.transform(sub[feat].values); ys = sub["y"].values
            lr.fit(Xs, ys)
            rn.append({"n": int(len(sub)),
                       "coef": lr.coef_.copy(),
                       "intercept": lr.intercept_.copy()})
        g_coef, g_inter = fedavg(rn)
        acc_r = accuracy_score(yte, global_predict(Xte_s))
        round_history.append({"round": r, "global_acc": float(acc_r)})
        print(f"  round {r}: global_acc={acc_r:.3f}")

    # --- Centralized upper-bound baseline (pool all node data) ---
    cen = LogisticRegression(max_iter=400, class_weight="balanced")
    cen.fit(scaler.transform(dtr[feat].values), dtr["y"].values)
    cen_acc = accuracy_score(yte, cen.predict(Xte_s))
    print(f"  Centralized baseline: acc={cen_acc:.3f}")

    save_metrics("federated", {
        "task": "federated_binary_classification",
        "dataset": "esp_features", "nodes": len(nodes),
        "held_out_test": int(len(yte)),
        "per_node": [{"esp_id": n["esp_id"], "n": n["n"],
                      "pos_rate": n["pos_rate"],
                      "local_acc": n["local_acc"]} for n in nodes],
        "fedavg_round1_acc": float(g1_acc),
        "fedavg_round1_f1": float(g1_f1),
        "fedavg_final_acc": float(round_history[-1]["global_acc"]),
        "centralized_baseline_acc": float(cen_acc),
        "round_history": round_history,
        "mechanism": "McMahan 2017 FedAvg (data-size-weighted), same math as "
                    "service FederatedLearningCoordinator.aggregate_round",
        "feature_names": feat,
        "note": "Real ESP data; global model evaluated on units unseen by any node."})
    print("Federated done.")

if __name__ == "__main__":
    main()
