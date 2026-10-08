"""Evaluate Phase 3B quality checks and metric movements under the 10k fit-cap."""
from __future__ import annotations
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from sklearn.datasets import make_blobs
from sklearn.metrics import roc_auc_score, precision_recall_curve, auc, recall_score
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest

from src.analytics.outlier_engine import run_segmentation

DATASET_CANDIDATES = [
    Path(r"C:\Users\rfate\Desktop\report\project\Project - 2\Datasets\phase-3A"),
    Path(r"C:\Users\rfate\Desktop\report\project\Project - 2\Datasets"),
    Path("data"),
    Path("../data"),
]

def get_path(*names):
    for base in DATASET_CANDIDATES:
        for n in names:
            p = base / n
            if p.exists():
                return p
    return None

def main():
    print("=" * 70)
    print("PHASE 3B QUALITY CHECKS RE-EVALUATION (10k FIT-CAP)")
    print("=" * 70)

    # 1. Blobs (600 rows)
    X, _ = make_blobs(n_samples=600, n_features=4, centers=3, cluster_std=0.5, center_box=(-20.0, 20.0), random_state=42)
    df_blob = pd.DataFrame(X, columns=[f"feat_{i}" for i in range(4)])
    res_b = run_segmentation(df_blob, random_state=42)
    print(f"Synthetic 3-Blobs: K* = {res_b['optimal_k']} via '{res_b['clustering_method']}'")
    print(f"  Silhouette scores: {res_b['silhouette_scores']}")
    print(f"  Compute latency: {res_b['timing_ms']['compute_total']} ms | Tier: {res_b['timing_ms']['budget_tier']}")

    # 2. Wholesale Customers (440 rows)
    pw = get_path("Wholesale customers data.csv", "Wholesale_customers_data.csv")
    if pw:
        df_w = pd.read_csv(pw)
        res_w = run_segmentation(df_w, random_state=42)
        print(f"Wholesale Customers: K* = {res_w['optimal_k']} via '{res_w['clustering_method']}'")
        print(f"  Compute latency: {res_w['timing_ms']['compute_total']} ms | Tier: {res_w['timing_ms']['budget_tier']}")

    # 3. Online Retail (4,338 customers)
    pr = get_path("online_retail.csv")
    if pr:
        df_r = pd.read_csv(pr, encoding="latin-1")
        res_r = run_segmentation(df_r, random_state=42)
        print(f"Online Retail (RFM): K* = {res_r['optimal_k']} via '{res_r['clustering_method']}'")
        print(f"  Compute latency: {res_r['timing_ms']['compute_total']} ms | Tier: {res_r['timing_ms']['budget_tier']}")

    # 4. Credit Card 20k Subsample
    pcc = get_path("creditcard.csv")
    if pcc:
        df_cc = pd.read_csv(pcc)
        total_rows = len(df_cc)
        rng = np.random.default_rng(42)
        sub_idx = rng.choice(total_rows, size=20000, replace=False)
        df_sub = df_cc.iloc[sub_idx].reset_index(drop=True)
        y_sub = df_sub["Class"].to_numpy(dtype=int)
        features = [c for c in df_sub.columns if c not in ("Time", "Class")]

        # Run live segmentation
        t0 = time.perf_counter()
        res_cc = run_segmentation(df_sub, random_state=42)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Evaluate model performance on 20k rows with 10k fit-cap
        # In run_segmentation, IsolationForest is fit on the 10,000-row sample
        Xs_sub = StandardScaler().fit_transform(df_sub[features].to_numpy(dtype=float))
        rng_cap = np.random.default_rng(42)
        fit_idx = rng_cap.choice(20000, size=10000, replace=False)
        fit_idx.sort()

        ifo_10k = IsolationForest(n_estimators=10, max_samples=min(256, 10000), contamination=0.03, random_state=42, n_jobs=1)
        ifo_10k.fit(Xs_sub[fit_idx])
        scores_10k = -ifo_10k.score_samples(Xs_sub)

        auc_roc = float(roc_auc_score(y_sub, scores_10k))
        prec_s, rec_s, _ = precision_recall_curve(y_sub, scores_10k)
        pr_auc = float(auc(rec_s, prec_s))
        thresh = np.percentile(scores_10k, 95)
        rec_5 = float(recall_score(y_sub, scores_10k >= thresh))

        print(f"Credit Card 20k (10k fit-cap):")
        print(f"  AUC-ROC: {auc_roc:.4f}")
        print(f"  PR-AUC: {pr_auc:.4f}")
        print(f"  Recall@5%: {rec_5*100:.1f}%")
        print(f"  Compute latency: {res_cc['timing_ms']['compute_total']} ms | Tier: {res_cc['timing_ms']['budget_tier']} (Budget: {res_cc['timing_ms']['budget']}ms, within: {res_cc['timing_ms']['within_budget']})")

if __name__ == "__main__":
    main()
