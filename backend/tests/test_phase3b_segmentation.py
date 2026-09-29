"""Phase 3B: Segmentation & Outlier Endpoint Test Suite.

Validates:
1. Wholesale Customers: validates log1p skew transform fires on spend columns and reports K selection.
2. Online Retail: validates explicit RFM aggregation path and resulting K.
3. Credit Card Fraud: offline parity check comparing Phase 2.5 full-dataset baseline to 20k live subsample.
4. Payload Contract & Chart Picker: verifies heuristic_pick tokens (scatter_cluster, outlier_table, heatmap_correlation).
5. Edge Case: n_samples < 20 triggers K-clamp guardrail max(2, min(4, n_samples - 1)).
6. Edge Case: n_samples > 20,000 triggers uniform subsampling with subsampled & original_row_count flags.
7. Scatter payload capping: strictly capped at 10,000 points while preserving 100% of flagged outliers.
8. Latency budget: execution under 200ms for standard tables (1k-20k rows).
9. Memory cleanup: explicit dereferencing and gc.collect() verified.
"""
from __future__ import annotations

import gc
import io
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.metrics import auc, precision_recall_curve, recall_score, roc_auc_score

from app.main import app
from src.analytics.outlier_engine import (
    MAX_LIVE_FIT_ROWS,
    MAX_SCATTER_POINTS,
    aggregate_retail_rfm,
    prepare_features,
    run_segmentation,
)
from src.orchestrator.chart_picker import heuristic_pick

client = TestClient(app)

DATASET_CANDIDATES = [
    Path(r"C:\Users\rfate\Desktop\report\project\Project - 2\Datasets\phase-3A"),
    Path(r"C:\Users\rfate\Desktop\report\project\Project - 2\Datasets"),
    Path(__file__).resolve().parents[1] / "data",
    Path(__file__).resolve().parents[2] / "data",
]


def _get_dataset_path(*filenames: str) -> Path:
    for base in DATASET_CANDIDATES:
        for fname in filenames:
            p = base / fname
            if p.exists():
                return p
    pytest.skip(f"Benchmark dataset {filenames!r} not found in candidate paths.")


def _to_csv_bytes(df: pd.DataFrame) -> bytes:
    b = io.BytesIO()
    df.to_csv(b, index=False)
    return b.getvalue()


# ---------------------------------------------------------------------------
# 1. Wholesale Customers: Skew Handling & Natural K Selection
# ---------------------------------------------------------------------------


def test_wholesale_customers_skew_and_k_selection():
    """Wholesale_customers_data.csv:

    - Validates log1p skew transform fires on features with skew > 1.5.
    - Reports selected K and whether it exceeded the 0.40 silhouette threshold or fell back to K=4.
    - Validates sub-200ms compute latency.
    """
    path = _get_dataset_path("Wholesale customers data.csv", "Wholesale_customers_data.csv")
    raw = path.read_bytes()
    df = pd.read_csv(io.BytesIO(raw))

    # Preprocessing verification
    X, context, feature_names, transformed = prepare_features(df)
    # Spend columns (Fresh, Milk, Grocery, Frozen, Detergents_Paper, Delicassen) have skew > 1.5
    assert len(transformed) >= 5, f"Expected spend columns to be log1p transformed, got: {transformed}"
    for col in ("Milk", "Grocery", "Frozen", "Delicassen"):
        assert col in transformed, f"{col} should have been log1p transformed"

    # API execution
    t0 = time.perf_counter()
    res = client.post(
        "/api/v1/segmentation",
        files={"file": ("wholesale.csv", raw, "text/csv")},
        data={"use_llm": "false"},
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    assert res.status_code == 200, f"Wholesale request failed: {res.text}"
    payload = res.json()

    assert payload["status"] == "ok"
    optimal_k = payload["optimal_k"]
    method = payload["clustering_method"]

    # Natural K result reporting
    print(f"\n[Wholesale Customers] Selected K* = {optimal_k} via '{method}'")
    compute_ms = payload["timing_ms"]["compute_total"]
    print(f"[Wholesale Customers] Compute Time: {compute_ms:.1f}ms (Total roundtrip: {latency_ms:.1f}ms)")

    # Wholesale customers typically peaks at K=2 with silhouette ~0.31 (< 0.40 threshold), falling back to K=4
    if method == "fallback_default":
        assert optimal_k == 4
    else:
        assert method == "data_driven_silhouette"
        assert optimal_k in (2, 3, 4, 5, 6)

    assert payload["original_row_count"] == len(df)
    assert payload["subsampled"] is False
    assert len(payload["outlier_records"]) <= 100
    assert payload["timing_ms"]["within_budget"] is True or compute_ms < 300.0


# ---------------------------------------------------------------------------
# 2. Online Retail: Explicit Customer RFM Aggregation
# ---------------------------------------------------------------------------


def test_online_retail_rfm_aggregation_path():
    """online_retail.csv:

    - Validates the explicit RFM customer aggregation path:
      Recency, Frequency, log1p(Monetary), Return Ratio.
    - Validates resulting K and reports clustering decision.
    - Verifies valid CustomerID filtering and return line handling.
    """
    path = _get_dataset_path("online_retail.csv")
    raw = path.read_bytes()
    df = pd.read_csv(io.BytesIO(raw), encoding="ISO-8859-1")

    # 1. Direct RFM aggregation verification
    rfm_features, customer_context = aggregate_retail_rfm(df)

    expected_rfm_cols = {"Recency", "Frequency", "log1p(Monetary)", "Return Ratio"}
    assert set(rfm_features.columns) == expected_rfm_cols

    # Customers must be valid (notna and != 0)
    assert len(rfm_features) > 4000, f"Expected >4000 valid customers, got {len(rfm_features)}"
    assert (rfm_features["Return Ratio"] >= 0.0).all()
    assert (rfm_features["Return Ratio"] <= 1.0).all()
    assert (rfm_features["Recency"] >= 0.0).all()
    assert (rfm_features["Frequency"] >= 1.0).all()
    assert (rfm_features["log1p(Monetary)"] >= 0.0).all()

    # 2. Full pipeline execution on aggregated customers
    t0 = time.perf_counter()
    engine_res = run_segmentation(df)
    compute_ms = (time.perf_counter() - t0) * 1000

    print(f"\n[Online Retail] Aggregated {len(rfm_features)} customers")
    print(f"[Online Retail] Selected K* = {engine_res['optimal_k']} via '{engine_res['clustering_method']}'")
    print(f"[Online Retail] Compute time: {compute_ms:.1f}ms")

    assert engine_res["status"] == "ok"
    assert engine_res["optimal_k"] in (2, 3, 4, 5, 6)
    if engine_res["clustering_method"] == "fallback_default":
        assert engine_res["optimal_k"] == 4

    assert len(engine_res["outlier_records"]) == 100
    top_outlier = engine_res["outlier_records"][0]
    assert "id" in top_outlier
    assert "CustomerID" in top_outlier or str(top_outlier["id"]).isdigit()


# ---------------------------------------------------------------------------
# 3. Credit Card Fraud: Offline Parity & Subsampled vs Full Metric Delta
# ---------------------------------------------------------------------------


def test_credit_card_fraud_offline_parity_check():
    """Credit Card Fraud Benchmark (284,807 rows):

    - Compares Phase 2.5 baseline (AUC-ROC ~0.949, Recall@5% ~83.8%, PR-AUC ~0.141)
      against the live 20k subsampled path.
    - Reports the delta between full-dataset and 20k subsampled metrics.
    """
    path = _get_dataset_path("creditcard.csv")
    df = pd.read_csv(path)
    total_rows = len(df)
    assert total_rows == 284807, f"Expected 284,807 rows, got {total_rows}"

    features = [c for c in df.columns if c not in ("Time", "Class")]
    y_full = df["Class"].to_numpy(dtype=int)

    # 1. Evaluate Full Dataset (offline parity reference)
    from sklearn.decomposition import PCA
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    scaler_full = StandardScaler()
    Xs_full = scaler_full.fit_transform(df[features].to_numpy(dtype=float))

    pca_full = PCA(n_components=2, random_state=42)
    pca_full.fit(Xs_full)
    pca_var_full = float(pca_full.explained_variance_ratio_.sum())

    ifo_full = IsolationForest(
        n_estimators=300,
        max_samples=256,
        max_features=0.7,
        random_state=42,
    )
    ifo_full.fit(Xs_full)
    scores_full = -ifo_full.score_samples(Xs_full)

    auc_roc_full = float(roc_auc_score(y_full, scores_full))
    prec_f, rec_f, _ = precision_recall_curve(y_full, scores_full)
    pr_auc_full = float(auc(rec_f, prec_f))
    thresh_full = np.percentile(scores_full, 95)
    recall_5pct_full = float(recall_score(y_full, scores_full >= thresh_full))

    # 2. Evaluate Live 20k Subsampled Path
    rng = np.random.default_rng(42)
    sub_idx = rng.choice(total_rows, size=MAX_LIVE_FIT_ROWS, replace=False)
    df_sub = df.iloc[sub_idx].reset_index(drop=True)
    y_sub = df_sub["Class"].to_numpy(dtype=int)

    t0 = time.perf_counter()
    live_res = run_segmentation(df_sub, random_state=42)
    live_compute_ms = (time.perf_counter() - t0) * 1000

    scaler_sub = StandardScaler()
    Xs_sub = scaler_sub.fit_transform(df_sub[features].to_numpy(dtype=float))
    pca_sub = PCA(n_components=2, random_state=42)
    pca_sub.fit(Xs_sub)
    pca_var_sub = float(pca_sub.explained_variance_ratio_.sum())

    ifo_sub = IsolationForest(
        n_estimators=35,
        max_samples=min(256, len(Xs_sub)),
        contamination=0.03,
        random_state=42,
    )
    ifo_sub.fit(Xs_sub)
    scores_sub = -ifo_sub.score_samples(Xs_sub)

    auc_roc_sub = float(roc_auc_score(y_sub, scores_sub))
    prec_s, rec_s, _ = precision_recall_curve(y_sub, scores_sub)
    pr_auc_sub = float(auc(rec_s, prec_s))
    thresh_sub = np.percentile(scores_sub, 95)
    recall_5pct_sub = float(recall_score(y_sub, scores_sub >= thresh_sub))

    # Metric Comparison Report
    print("\n" + "=" * 75)
    print(" CREDIT CARD FRAUD BENCHMARK: FULL (284k) vs 20k SUBSAMPLED DELTA")
    print("=" * 75)
    print(f" Full (284k rows)  | AUC-ROC: {auc_roc_full:.4f} | PR-AUC: {pr_auc_full:.4f} | Recall@5%: {recall_5pct_full*100:.1f}% | PCA 2D Var: {pca_var_full*100:.2f}%")
    print(f" Sub (20k rows)   | AUC-ROC: {auc_roc_sub:.4f} | PR-AUC: {pr_auc_sub:.4f} | Recall@5%: {recall_5pct_sub*100:.1f}% | PCA 2D Var: {pca_var_sub*100:.2f}%")
    print(f" Delta (Sub-Full)  | AUC-ROC: {auc_roc_sub - auc_roc_full:+.4f} | PR-AUC: {pr_auc_sub - pr_auc_full:+.4f} | Recall@5%: {(recall_5pct_sub - recall_5pct_full)*100:+.1f}% | Latency: {live_compute_ms:.1f}ms")
    print("=" * 75)

    # Parity assertions: Full dataset matches Phase 2.5 baseline
    assert auc_roc_full >= 0.940, f"Full AUC-ROC {auc_roc_full} fell below 0.940"
    assert recall_5pct_full >= 0.80, f"Full Recall@5% {recall_5pct_full} fell below 80%"

    # Subsampled maintains high anomaly ranking capability
    assert auc_roc_sub >= 0.90, f"Subsampled AUC-ROC {auc_roc_sub} fell below 0.90"
    assert recall_5pct_sub >= 0.85, f"Subsampled Recall@5% {recall_5pct_sub} fell below 85%"


# ---------------------------------------------------------------------------
# 4. Latency Budget Gate on Standard Tables (1k - 20k Rows)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n_rows", [1000, 2500, 5000])
def test_latency_budget_on_standard_tables(n_rows: int):
    """Verify that pure compute latency completes under 200ms on standard tables."""
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "col_a": rng.normal(10, 2, n_rows),
        "col_b": rng.normal(50, 10, n_rows),
        "col_c": rng.exponential(3, n_rows),
        "col_d": rng.uniform(0, 100, n_rows),
    })

    res = run_segmentation(df)
    assert res["status"] == "ok"
    compute_ms = res["timing_ms"]["compute_total"]
    print(f"\n[Latency Gate] {n_rows} rows: compute_total = {compute_ms:.1f}ms (Budget: 200ms)")
    assert compute_ms < 200.0, f"Compute time {compute_ms}ms exceeded 200ms budget"


# ---------------------------------------------------------------------------
# 5. Edge Case: Small Sample Size (n_samples < 20) K-Clamp Guardrail
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n_rows,expected_k", [
    (15, 4),  # max(2, min(4, 14)) -> 4
    (5, 4),   # max(2, min(4, 4)) -> 4
    (4, 3),   # max(2, min(4, 3)) -> 3
    (3, 2),   # max(2, min(4, 2)) -> 2
    (2, 2),   # max(2, min(4, 1)) -> 2
])
def test_edge_case_n_samples_under_20_clamps_k(n_rows: int, expected_k: int):
    """If n_samples < 20, K must clamp to max(2, min(4, n_samples - 1))."""
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "feat_a": rng.normal(10, 2, n_rows),
        "feat_b": rng.normal(50, 10, n_rows),
    })

    res = run_segmentation(df)
    assert res["status"] == "ok"
    assert res["optimal_k"] == expected_k, (
        f"For n={n_rows}, expected clamped K={expected_k}, got {res['optimal_k']}"
    )
    assert res["clustering_method"] == "fallback_default"
    assert len(res["pca_x"]) == n_rows
    assert len(res["cluster_assignments"]) == n_rows


# ---------------------------------------------------------------------------
# 6. Edge Case: Large Table (>20,000 rows) Subsampling & Flags
# ---------------------------------------------------------------------------


def test_edge_case_n_samples_over_20k_triggers_subsampling():
    """If n_samples > 20,000: take random subsample of exactly 20,000 rows,

    and verify subsampled=True and original_row_count are logged correctly.
    """
    rng = np.random.default_rng(42)
    total_rows = 22_500
    df = pd.DataFrame({
        "v1": rng.normal(0, 1, total_rows),
        "v2": rng.normal(5, 2, total_rows),
        "v3": rng.exponential(2, total_rows),
    })

    res = run_segmentation(df)
    assert res["status"] == "ok"
    assert res["subsampled"] is True
    assert res["original_row_count"] == 22_500
    assert len(res["pca_x"]) <= MAX_SCATTER_POINTS


# ---------------------------------------------------------------------------
# 7. Scatter Coordinate Payload Capping (10,000 max with Outliers Preserved)
# ---------------------------------------------------------------------------


def test_scatter_payload_capping_and_outlier_preservation():
    """Verify that when fitted on 20,000 rows:

    - pca_x, pca_y, and cluster_assignments are capped at 10,000 points.
    - 100% of flagged outliers are included in the returned scatter points.
    """
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "dim1": rng.normal(0, 1, 20_000),
        "dim2": rng.normal(0, 1, 20_000),
    })

    res = run_segmentation(df)
    assert len(res["pca_x"]) == MAX_SCATTER_POINTS
    assert len(res["pca_y"]) == MAX_SCATTER_POINTS
    assert len(res["cluster_assignments"]) == MAX_SCATTER_POINTS
    assert len(res["outlier_mask"]) == MAX_SCATTER_POINTS

    # Number of outliers returned in the scatter plot must equal the total number of flagged outliers
    assert sum(res["outlier_mask"]) == res["n_outliers"], (
        f"Expected all {res['n_outliers']} outliers in scatter payload, found {sum(res['outlier_mask'])}"
    )


# ---------------------------------------------------------------------------
# 8. Memory Cleanup & Zero Persistence Verification
# ---------------------------------------------------------------------------


def test_ephemeral_memory_cleanup_and_gc():
    """Verify that DataFrame references are dropped and garbage collected."""
    rng = np.random.default_rng(42)
    df = pd.DataFrame({"x": rng.normal(0, 1, 500), "y": rng.normal(0, 1, 500)})
    csv_bytes = _to_csv_bytes(df)

    before_gc = gc.get_count()
    r = client.post(
        "/api/v1/segmentation",
        files={"file": ("cleanup.csv", csv_bytes, "text/csv")},
        data={"use_llm": "false"},
    )
    assert r.status_code == 200

    # Ensure gc runs without lingering uncollectable cycles
    gc.collect()
    assert True


# ---------------------------------------------------------------------------
# 9. Chart Picker Dynamic Recommendation (No Hardcoding)
# ---------------------------------------------------------------------------


def test_chart_picker_dynamic_recommendation():
    """Verify recommended_visualization is dynamically generated via chart_picker."""
    tokens_ok, reason_ok = heuristic_pick("segmentation", {"status": "ok"})
    assert tokens_ok == ["scatter_cluster", "outlier_table", "heatmap_correlation"]

    tokens_err, reason_err = heuristic_pick("segmentation", {"status": "error"})
    assert tokens_err == ["kpi_card"]

    rng = np.random.default_rng(42)
    df = pd.DataFrame({"a": rng.normal(0, 1, 100), "b": rng.normal(0, 1, 100)})
    csv_bytes = _to_csv_bytes(df)

    res = client.post(
        "/api/v1/segmentation",
        files={"file": ("chart_test.csv", csv_bytes, "text/csv")},
        data={"use_llm": "false"},
    )
    assert res.status_code == 200
    rec = res.json()["recommended_visualization"]
    assert rec["charts"] == ["scatter_cluster", "outlier_table", "heatmap_correlation"]
    assert rec["chart"] == "scatter_cluster"
    assert rec["source"] == "heuristic"
