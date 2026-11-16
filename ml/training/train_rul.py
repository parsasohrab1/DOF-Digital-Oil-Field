"""
Phase 4d — Train & evaluate RUL (Remaining Useful Life) on NASA C-MAPSS FD001.

Leakage-safe:
  * Train/val split by ENGINE UNIT (no engine in both) — 80 train / 20 val.
  * StandardScaler fit on train only.
  * Test = official FD001 test set: last observed cycle of each of 100 engines
    with the published true RUL. This is the standard FD001 protocol.
  * RUL target is piece-wise clipped at 125 (standard practice, Ramasso 2013);
    metrics are reported against the TRUE unclipped test RUL.

Algorithms: RandomForestRegressor, GradientBoostingRegressor, XGBoost.
Metrics (real): RMSE, MAE, R². Saved as rul_turbofan.pkl (+ scaler + meta).
Run:  python -I train_rul.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import joblib, matplotlib.pyplot as plt, numpy as np, pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
from common import CLEANED, MODELS, load_specs, save_meta, save_metrics, save_plot

RUL_CLIP = 125

def main():
    specs = load_specs(); sp = specs["datasets"]["cmapss"]
    feat = sp["features"]; print(f"RUL on C-MAPSS FD001 — {len(feat)} features, clip={RUL_CLIP}")
    tr = pd.read_csv(CLEANED/"cmapss_fd001_train_split.csv")
    va = pd.read_csv(CLEANED/"cmapss_fd001_val_split.csv")
    te = pd.read_csv(CLEANED/"cmapss_fd001_test.csv")
    def prep(d): 
        y = d["RUL"].clip(upper=RUL_CLIP).values
        return d[feat].values, y
    Xtr, ytr = prep(tr); Xva, yva_real = va[feat].values, va["RUL"].values
    Xte, yte_real = te[feat].values, te["RUL"].values
    scaler = StandardScaler().fit(Xtr)
    Xtr_s = scaler.transform(Xtr); Xva_s = scaler.transform(Xva); Xte_s = scaler.transform(Xte)
    ytr_c = tr["RUL"].clip(upper=RUL_CLIP).values
    print(f"train engines={tr['unit'].nunique()} val={va['unit'].nunique()} test={len(te)}")

    models = {
        "random_forest": RandomForestRegressor(n_estimators=300, max_depth=20,
            min_samples_leaf=5, random_state=42, n_jobs=-1),
        "gradient_boosting": GradientBoostingRegressor(n_estimators=200, max_depth=4,
            learning_rate=0.1, random_state=42),
        "xgboost": xgb.XGBRegressor(n_estimators=300, max_depth=6, learning_rate=0.1,
            subsample=0.9, random_state=42, n_jobs=-1),
    }
    results = {}
    for name, m in models.items():
        m.fit(Xtr_s, ytr_c)
        pred = m.predict(Xte_s)
        rmse = float(np.sqrt(mean_squared_error(yte_real, pred)))
        mae = float(mean_absolute_error(yte_real, pred))
        r2 = float(r2_score(yte_real, pred))
        results[name] = {"rmse": rmse, "mae": mae, "r2": r2}
        print(f"  {name:18s} RMSE={rmse:.2f} MAE={mae:.2f} R²={r2:.3f}")

    best = max(results, key=lambda k: results[k]["r2"])
    best_model = models[best]
    print(f"  -> selected: {best}")
    joblib.dump(best_model, MODELS/"rul_turbofan.pkl")
    joblib.dump(scaler, MODELS/"rul_turbofan_scaler.pkl")
    save_meta("rul_turbofan", {"feature_names": feat, "model_type": best,
        "rul_clip": RUL_CLIP, "metrics": results[best],
        "data_origin": "NASA C-MAPSS FD001 (simulated turbofan)",
        "n_train_engines": int(tr['unit'].nunique()), "n_test": int(len(te))})

    pred = best_model.predict(Xte_s)
    fig, ax = plt.subplots(figsize=(6,5))
    ax.scatter(yte_real, pred, s=18, alpha=0.6)
    lims = [min(yte_real.min(), pred.min()), max(yte_real.max(), pred.max())]
    ax.plot(lims, lims, "r--", alpha=0.7)
    ax.set_xlabel("True RUL (cycles)"); ax.set_ylabel("Predicted RUL")
    ax.set_title(f"RUL {best}: RMSE={results[best]['rmse']:.1f} R²={results[best]['r2']:.3f}")
    save_plot(fig, "rul_pred_vs_true")

    save_metrics("rul", {"task":"regression","dataset":"cmapss_fd001",
        "split":{"train_engines":int(tr['unit'].nunique()),"test_engines":int(len(te))},
        "rul_clip":RUL_CLIP,"models":results,"selected_production_model":best,
        "feature_names":feat,"note":"Test = official FD001 held-out set with true RUL."})
    print("RUL done.")

if __name__=="__main__": main()
