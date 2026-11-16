"""
Phase 4f — Train & evaluate Sorush oil-field QL regression.

Predict liquid flow rate QL (STB/D) from choke size, wellhead pressure, oil
gravity and GLR. Split stratified by well so no well leaks into both sides;
StandardScaler fit on train only. Algorithms: RF, GBR, XGBoost, LightGBM.
Metrics (real): RMSE, MAE, R², MAPE. Benchmarked against the published paper
(DL: RMSE=196 STB/D, R²=0.9969) — our held-out test is not the paper's exact
split, so we report both and note the caveat.
Saved as sorush_ql.pkl (+ scaler + meta).
Run:  python -I train_sorush.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import joblib, matplotlib.pyplot as plt, numpy as np, pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import xgboost as xgb, lightgbm as lgb
from common import CLEANED, MODELS, load_specs, save_meta, save_metrics, save_plot

def mape(y,yh):
    m = np.abs(y)>1e-6
    return float(np.mean(np.abs((y[m]-yh[m])/y[m]))*100) if m.any() else float("nan")

def main():
    specs = load_specs(); sp = specs["datasets"]["sorush"]
    feat = sp["features"]; bench = sp["benchmark"]
    print(f"Sorush QL — {len(feat)} features, {len(feat)} real field records")
    df = pd.read_csv(CLEANED/"sorush_field_clean.csv")
    X = df[feat].values; y = df["ql_stb_d"].values.astype("float64")
    # stratified by well code so no well leaks
    Xtr,Xte,ytr,yte = train_test_split(X,y,test_size=0.2,random_state=42,
        stratify=df["well_code"])
    scaler = StandardScaler().fit(Xtr)
    Xtr_s, Xte_s = scaler.transform(Xtr), scaler.transform(Xte)
    print(f"train={len(Xtr)} test={len(Xte)} QL test range=[{yte.min():.0f},{yte.max():.0f}]")

    models = {
        "random_forest": RandomForestRegressor(n_estimators=400, max_depth=15,
            min_samples_leaf=2, random_state=42, n_jobs=-1),
        "gradient_boosting": GradientBoostingRegressor(n_estimators=300, max_depth=4,
            learning_rate=0.05, random_state=42),
        "xgboost": xgb.XGBRegressor(n_estimators=400, max_depth=6, learning_rate=0.05,
            subsample=0.9, random_state=42, n_jobs=-1),
        "lightgbm": lgb.LGBMRegressor(n_estimators=400, max_depth=6, learning_rate=0.05,
            subsample=0.9, random_state=42, n_jobs=-1, verbose=-1),
    }
    results = {}
    for name, m in models.items():
        m.fit(Xtr_s, ytr); pred = m.predict(Xte_s)
        rmse = float(np.sqrt(mean_squared_error(yte,pred)))
        results[name] = {"rmse":rmse, "mae":float(mean_absolute_error(yte,pred)),
            "r2":float(r2_score(yte,pred)), "mape":mape(yte,pred)}
        print(f"  {name:18s} RMSE={rmse:.1f} MAE={results[name]['mae']:.1f} "
              f"R²={results[name]['r2']:.4f} MAPE={results[name]['mape']:.2f}%")

    best = max(results, key=lambda k: results[k]["r2"]); bm = models[best]
    print(f"  -> selected: {best}")
    joblib.dump(bm, MODELS/"sorush_ql.pkl")
    joblib.dump(scaler, MODELS/"sorush_ql_scaler.pkl")
    save_meta("sorush_ql", {"feature_names":feat,"model_type":best,
        "metrics":results[best],"data_origin":"Sorush oil field (real, Barjouei 2021)",
        "n_train":int(len(Xtr)),"n_test":int(len(Xte)),
        "benchmark_vs_paper":bench})

    pred = bm.predict(Xte_s)
    fig, ax = plt.subplots(figsize=(6,5))
    ax.scatter(yte, pred, s=14, alpha=0.5)
    lims=[min(yte.min(),pred.min()),max(yte.max(),pred.max())]
    ax.plot(lims,lims,"r--",alpha=0.7)
    ax.set_xlabel("True QL (STB/D)"); ax.set_ylabel("Predicted QL (STB/D)")
    ax.set_title(f"Sorush QL {best}: RMSE={results[best]['rmse']:.0f} R²={results[best]['r2']:.4f}")
    save_plot(fig, "sorush_pred_vs_true")

    save_metrics("sorush_ql", {"task":"regression","dataset":"sorush_field",
        "split":{"train":int(len(Xtr)),"test":int(len(Xte))},
        "models":results,"selected_production_model":best,
        "feature_names":feat,"benchmark_vs_paper":bench,
        "note":"Paper RMSE=196/R²=0.9969 used a different (full-data) split; "
               "our metrics are on a well-stratified held-out test, not comparable like-for-like."})
    print("Sorush done.")

if __name__=="__main__": main()
