"""
Phase 4e — Train & evaluate Bearing Fault Classification on CWRU.

4 classes (0=Normal, 1=Inner-Race, 2=Outer-Race, 3=Ball). Stratified split,
StandardScaler fit on train only. Algorithms: RF, XGBoost, LightGBM.
Metrics: accuracy, macro/weighted F1, ROC-AUC, confusion matrix.
Saved as bearing_fault.pkl (+ scaler + meta). Standalone model (no service
endpoint exists for it — documented).
Run:  python -I train_bearing.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import joblib, matplotlib.pyplot as plt, numpy as np, pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
    precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.preprocessing import StandardScaler, label_binarize
import xgboost as xgb, lightgbm as lgb
from common import CLEANED, MODELS, load_specs, save_meta, save_metrics, save_plot

def main():
    specs = load_specs(); sp = specs["datasets"]["cwru"]
    feat, label_map = sp["features"], sp["label_map"]
    inv = {v:k for k,v in label_map.items()}
    print(f"CWRU bearing fault — {len(feat)} features, 4 classes")
    df = pd.read_csv(CLEANED/"cwru_bearing_clean.csv")
    X, y = df[feat].values, df["label"].values
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr, te = next(sss.split(X,y))
    Xtr,Xte,ytr,yte = X[tr],X[te],y[tr],y[te]
    scaler = StandardScaler().fit(Xtr)
    Xtr_s, Xte_s = scaler.transform(Xtr), scaler.transform(Xte)
    print(f"train={len(Xtr)} test={len(Xte)} dist={np.bincount(yte).tolist()}")

    models = {
        "random_forest": RandomForestClassifier(n_estimators=300, max_depth=12,
            random_state=42, n_jobs=-1),
        "xgboost": xgb.XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1,
            eval_metric="mlogloss", random_state=42, n_jobs=-1),
        "lightgbm": lgb.LGBMClassifier(n_estimators=300, max_depth=6, learning_rate=0.1,
            random_state=42, n_jobs=-1, verbose=-1),
    }
    yte_bin = label_binarize(yte, classes=[0,1,2,3])
    results = {}
    for name, m in models.items():
        m.fit(Xtr_s, ytr)
        pred = m.predict(Xte_s); proba = m.predict_proba(Xte_s)
        acc = accuracy_score(yte, pred); mf1 = f1_score(yte,pred,average="macro")
        wf1 = f1_score(yte,pred,average="weighted")
        auc = roc_auc_score(yte_bin, proba, multi_class="ovr", average="weighted")
        results[name] = {"accuracy":float(acc),"macro_f1":float(mf1),
            "weighted_f1":float(wf1),"roc_auc":float(auc),
            "precision_macro":float(precision_score(yte,pred,average="macro")),
            "recall_macro":float(recall_score(yte,pred,average="macro")),
            "confusion_matrix":confusion_matrix(yte,pred).tolist()}
        print(f"  {name:14s} acc={acc:.3f} macroF1={mf1:.3f} AUC={auc:.3f}")

    best = max(results, key=lambda k: results[k]["macro_f1"]); bm = models[best]
    print(f"  -> selected: {best}")
    joblib.dump(bm, MODELS/"bearing_fault.pkl")
    joblib.dump(scaler, MODELS/"bearing_fault_scaler.pkl")
    save_meta("bearing_fault", {"feature_names":feat,"label_map":label_map,
        "model_type":best,"metrics":results[best],
        "data_origin":"CWRU bearing lab data","n_train":int(len(Xtr))})

    pred = bm.predict(Xte_s); cm = np.array(confusion_matrix(yte,pred))
    fig, ax = plt.subplots(figsize=(5,4))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(4)); ax.set_yticks(range(4))
    ax.set_xticklabels([inv[i] for i in range(4)], rotation=30, ha="right")
    ax.set_yticklabels([inv[i] for i in range(4)])
    ax.set_xlabel("Predicted"); ax.set_ylabel("True")
    ax.set_title(f"CWRU Bearing {best}: acc={results[best]['accuracy']:.3f}")
    for i in range(4):
        for j in range(4):
            ax.text(j,i,cm[i,j],ha="center",va="center",
                color="white" if cm[i,j]>cm.max()/2 else "black")
    save_plot(fig, "bearing_confusion_matrix")

    save_metrics("bearing_fault", {"task":"classification","dataset":"cwru",
        "split":{"train":int(len(Xtr)),"test":int(len(Xte))},
        "label_map":label_map,"models":results,"selected_production_model":best,
        "feature_names":feat})
    print("Bearing done.")

if __name__=="__main__": main()
