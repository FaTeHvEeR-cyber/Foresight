"""Engine B Analytics: Segmentation, Clustering, and Outlier Engine.

Implements pure in-memory training and fast inference for:
1. Data-driven KMeans cluster selection (K in {2..6}, peak silhouette >= 0.40 or fallback K=4).
2. StandardScaler + 2D PCA projection with scatter payload capping (10,000 max, outliers preserved).
3. IsolationForest anomaly detection (contamination=0.03 fixed, top 100 outlier records with row context).
4. Retail RFM aggregation for transaction datasets (Recency, Frequency, log1p(Monetary), Return Ratio).
5. Pre-scaling correlation matrix with high-variance column truncation (cap 25 cols).
6. 20,000 row ceiling with uniform random subsampling.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import pairwise_distances, silhouette_score
from sklearn.preprocessing import StandardScaler
from sklearn.utils import check_random_state

from src.analytics import feature_pipeline as fp

logger = logging.getLogger("outlier_engine")

MAX_LIVE_FIT_ROWS = 20_000
MAX_SCATTER_POINTS = 10_000
MAX_OUTLIER_RECORDS = 100
MAX_CORR_COLUMNS = 25
FIXED_CONTAMINATION = 0.03
SILHOUETTE_THRESHOLD = 0.40

# Pre-warm Windows OpenMP / threadpool DLLs at module import time to eliminate cold-start latency spikes
try:
    _warm_X = np.ones((300, 4), dtype=np.float32)
    _warm_X[150:] = -1.0
    _warm_km = KMeans(n_clusters=2, n_init=1, max_iter=2, algorithm="elkan").fit(_warm_X)
    _ = _warm_km.predict(_warm_X)
    _ = silhouette_score(_warm_X, _warm_km.labels_)
    _warm_iso = IsolationForest(n_estimators=5, max_samples=128, random_state=42).fit(_warm_X)
    _ = _warm_iso.score_samples(_warm_X)
except Exception:
    pass


def _is_online_retail_transactions(df: pd.DataFrame) -> bool:
    """Check if the dataframe represents Online Retail transaction logs with CustomerID."""
    has_retail_cols = fp.is_retail_transactions(df)
    has_customer = fp.find_col(df, "customerid", "customer_id", "client_id") is not None
    return bool(has_retail_cols and has_customer)


def aggregate_retail_rfm(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate raw retail transaction logs into a customer-level RFM matrix.

    Features generated per valid CustomerID:
    - Recency: Days between latest transaction and dataset reference date.
    - Frequency: Unique invoice / transaction count.
    - log1p(Monetary): log1p of total positive spending.
    - Return Ratio: Ratio of return/cancellation lines to total lines (bounded 0.0 - 1.0).

    Returns:
        (rfm_features_df, full_customer_df_with_id)
    """
    cid_col = fp.find_col(df, "customerid", "customer_id", "client_id")
    inv_col = fp.find_col(df, "invoiceno", "invoice_no", "invoice")
    qty_col = fp.find_col(df, "quantity", "qty")
    price_col = fp.find_col(df, "unitprice", "price")
    dt_col = fp.find_col(df, "invoicedate", "invoice_date", "date")

    assert cid_col and inv_col and qty_col and price_col and dt_col

    sub = df[[cid_col, inv_col, qty_col, price_col, dt_col]].copy()
    sub.columns = ["CustomerID", "InvoiceNo", "Quantity", "UnitPrice", "InvoiceDate"]

    # Filter valid CustomerIDs
    sub = sub[sub["CustomerID"].notna()].copy()
    # Normalize CustomerID to string
    try:
        sub["CustomerID"] = sub["CustomerID"].astype(int).astype(str)
    except Exception:
        sub["CustomerID"] = sub["CustomerID"].astype(str)

    sub = sub[sub["CustomerID"] != "0"].copy()

    # Parse dates
    dates, _ = fp.parse_dates(sub["InvoiceDate"])
    sub["InvoiceDate"] = dates

    # Compute line totals and return indicator
    qty_num = pd.to_numeric(sub["Quantity"], errors="coerce").fillna(0.0)
    price_num = pd.to_numeric(sub["UnitPrice"], errors="coerce").fillna(0.0)
    sub["LineTotal"] = qty_num * price_num

    inv_str = sub["InvoiceNo"].astype(str)
    sub["IsReturn"] = (inv_str.str.startswith("C")) | (qty_num < 0)

    # Reference date is 1 day after the latest date in the entire dataset
    max_date = sub["InvoiceDate"].dropna().max()
    ref_date = max_date + pd.Timedelta(days=1)

    # Group by customer
    grouped = sub.groupby("CustomerID").agg(
        last_date=("InvoiceDate", "max"),
        frequency=("InvoiceNo", "nunique"),
        monetary=("LineTotal", lambda s: float(s[s > 0].sum())),
        total_lines=("IsReturn", "count"),
        return_lines=("IsReturn", "sum"),
    )

    recency = (ref_date - grouped["last_date"]).dt.days.fillna(0).astype(float)
    freq = grouped["frequency"].astype(float)
    log_monetary = np.log1p(np.maximum(0.0, grouped["monetary"].to_numpy(dtype=float)))
    return_ratio = np.where(
        grouped["total_lines"] > 0,
        grouped["return_lines"] / grouped["total_lines"],
        0.0,
    )

    rfm_df = pd.DataFrame(
        {
            "Recency": recency.values,
            "Frequency": freq.values,
            "log1p(Monetary)": log_monetary,
            "Return Ratio": return_ratio,
        },
        index=grouped.index,
    )

    full_customer_df = pd.DataFrame(
        {
            "CustomerID": grouped.index,
            "Recency": recency.values,
            "Frequency": freq.values,
            "Monetary": grouped["monetary"].values,
            "log1p(Monetary)": log_monetary,
            "Return Ratio": np.round(return_ratio, 4),
        },
        index=grouped.index,
    )

    return rfm_df, full_customer_df


def prepare_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, List[str], List[str]]:
    """Inspect and extract numeric features, applying RFM aggregation and skew transforms.

    Returns:
        (X_features, original_context_df, feature_names, transformed_columns)
    """
    transformed_cols: List[str] = []

    # 1. Retail RFM special aggregation
    if _is_online_retail_transactions(df):
        rfm_features, original_context = aggregate_retail_rfm(df)
        X = rfm_features.copy()
        # Skew handling on RFM features (except log1p(Monetary) which is already transformed)
        for col in ["Recency", "Frequency", "Return Ratio"]:
            skew_val = float(X[col].skew())
            if skew_val > 1.5:
                X[col] = np.log1p(np.maximum(0.0, X[col].to_numpy(dtype=float)))
                transformed_cols.append(col)
        return X, original_context, list(X.columns), transformed_cols

    # 2. Generic Tabular Processing
    context_df = df.copy()

    # Drop explicit identifier columns
    id_cols = set(fp.detect_id_columns(context_df))
    numeric_cols = [
        c
        for c in context_df.columns
        if pd.api.types.is_numeric_dtype(context_df[c])
        and not pd.api.types.is_bool_dtype(context_df[c])
    ]

    chosen_cols = [c for c in numeric_cols if c not in id_cols]
    if not chosen_cols:
        chosen_cols = numeric_cols

    if not chosen_cols:
        raise ValueError("No numeric columns available in uploaded dataset for segmentation.")

    X = context_df[chosen_cols].copy().astype(float)
    # Fill any isolated NaNs with median
    if X.isna().any().any():
        X = X.fillna(X.median())

    # Drop columns that have zero variance
    variances = X.var(axis=0)
    valid_cols = variances[variances > 1e-12].index.tolist()
    if valid_cols:
        X = X[valid_cols]

    # Skew handling: log1p for skew > 1.5 (on non-negative arrays)
    for col in X.columns:
        col_vals = X[col].to_numpy(dtype=float)
        skew_val = float(pd.Series(col_vals).skew())
        if skew_val > 1.5:
            if np.all(col_vals >= 0.0):
                X[col] = np.log1p(col_vals)
                transformed_cols.append(col)
            elif np.min(col_vals) > -1.0:
                X[col] = np.log1p(np.maximum(0.0, col_vals))
                transformed_cols.append(col)

    return X, context_df, list(X.columns), transformed_cols


def compute_correlation_matrix(
    X: pd.DataFrame, max_cols: int = MAX_CORR_COLUMNS
) -> Tuple[Dict[str, Any], bool]:
    """Compute Pearson correlation matrix pre-scaling, capping at max_cols by variance."""
    total_cols = X.shape[1]
    if total_cols <= max_cols:
        selected_cols = list(X.columns)
        truncated = False
    else:
        variances = X.var(axis=0)
        selected_cols = variances.nlargest(max_cols).index.tolist()
        truncated = True

    if len(selected_cols) == 0:
        return {"columns": [], "values": [], "points": [], "truncated": False}, False

    sub_X = X[selected_cols]
    corr_df = sub_X.corr().fillna(0.0)

    columns = list(selected_cols)
    values: List[List[float]] = []
    points: List[Dict[str, Any]] = []

    for i, col_i in enumerate(columns):
        row_vals: List[float] = []
        for j, col_j in enumerate(columns):
            val = round(float(corr_df.iloc[i, j]), 4)
            if np.isnan(val) or np.isinf(val):
                val = 0.0
            row_vals.append(val)
            points.append({"x": str(col_i), "y": str(col_j), "value": val})
        values.append(row_vals)

    matrix_dict = {
        "columns": columns,
        "values": values,
        "points": points,
        "truncated": truncated,
    }
    return matrix_dict, truncated


def select_optimal_k(
    X_scaled: np.ndarray, n_samples: int, random_state: int = 42
) -> Tuple[int, str, Dict[int, float], Dict[int, Any]]:
    """Determine optimal cluster count K via subsampled silhouette or fallback.

    Rules (§1):
    - Candidate range: K in {2, 3, 4, 5, 6}.
    - If n_samples < 20: clamp K to max(2, min(4, n_samples - 1)), method='fallback_default'.
    - Score each with subsampled silhouette:
      silhouette_score(X_scaled, labels, sample_size=min(1000, n_samples), random_state=42)
    - If peak silhouette >= 0.40 -> adopt as K*, method='data_driven_silhouette'.
    - Else -> fallback K = 4, method='fallback_default'.
    """
    # Edge guardrail: n_samples < 20
    if n_samples < 20:
        clamped_k = max(2, min(4, max(1, n_samples - 1)))
        km_edge = KMeans(n_clusters=clamped_k, random_state=random_state, n_init=1, max_iter=8, tol=1e-2, algorithm="elkan")
        km_edge.fit(X_scaled)
        return clamped_k, "fallback_default", {}, {clamped_k: km_edge}

    candidate_ks = [2, 3, 4, 5, 6]
    sample_size = min(1000, n_samples)

    silhouette_scores: Dict[int, float] = {}
    fitted_models: Dict[int, Any] = {}
    best_k = 4
    best_score = -1.0

    # Subsample indices for silhouette scoring matching sklearn silhouette_score(X, labels, sample_size=..., random_state=42)
    rng = check_random_state(random_state)
    sample_idx = rng.permutation(n_samples)[:sample_size]
    X_sub = np.ascontiguousarray(X_scaled[sample_idx])
    dist_matrix = pairwise_distances(X_sub, metric="euclidean")

    # Sequential fit avoids GIL and OpenMP thread thrashing on Windows
    for k in candidate_ks:
        if k >= n_samples:
            continue
        try:
            km = KMeans(n_clusters=k, random_state=random_state, n_init=1, max_iter=7, tol=2e-2, algorithm="elkan")
            labels = km.fit_predict(X_scaled)
            fitted_models[k] = km
            sub_labels = labels[sample_idx]
            if len(np.unique(sub_labels)) < 2:
                continue
            score = float(
                silhouette_score(
                    dist_matrix,
                    sub_labels,
                    metric="precomputed",
                )
            )
            silhouette_scores[k] = round(score, 4)
            if score > best_score:
                best_score = score
                best_k = k
        except Exception as e:
            logger.warning(f"Error computing silhouette for K={k}: {e}")

    # Ensure fallback model K=4 is fit if not present
    if 4 not in fitted_models and 4 < n_samples:
        km_fallback = KMeans(n_clusters=4, random_state=random_state, n_init=1, max_iter=7, tol=2e-2, algorithm="elkan")
        km_fallback.fit(X_scaled)
        fitted_models[4] = km_fallback

    if best_score >= SILHOUETTE_THRESHOLD:
        return best_k, "data_driven_silhouette", silhouette_scores, fitted_models

    return 4, "fallback_default", silhouette_scores, fitted_models


def run_segmentation(
    df: pd.DataFrame,
    random_state: int = 42,
    n_estimators_iso: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute complete segmentation, clustering, and outlier detection workflow.

    Args:
        df: Input tabular dataframe.
        random_state: Random seed for deterministic reproducibility.
        n_estimators_iso: Number of trees for IsolationForest. Default auto-calibrated
            (10 trees to guarantee sub-200ms budget).

    Returns:
        Dictionary matching the SegmentationResponse schema.
    """
    t0 = time.perf_counter()

    # 1. Preprocessing & Feature Selection
    X_features, original_context, feature_names, transformed_cols = prepare_features(df)
    n_samples_raw = len(X_features)
    t_prep = time.perf_counter()

    # 2. Compute pre-scaling correlation matrix
    corr_matrix, corr_truncated = compute_correlation_matrix(
        X_features, max_cols=MAX_CORR_COLUMNS
    )

    # 3. Row-Cap & Subsampling (§4)
    # Hard ceiling: 20,000 rows for live per-request fit path
    if n_samples_raw > MAX_LIVE_FIT_ROWS:
        subsampled = True
        rng = np.random.default_rng(random_state)
        sub_indices = rng.choice(n_samples_raw, size=MAX_LIVE_FIT_ROWS, replace=False)
        sub_indices.sort()
        X_fit = X_features.iloc[sub_indices].reset_index(drop=True)
        context_fit = original_context.iloc[sub_indices].reset_index(drop=True)
    else:
        subsampled = False
        X_fit = X_features.reset_index(drop=True)
        context_fit = original_context.reset_index(drop=True)

    n_fit = len(X_fit)

    # 4. Standard Scaling (contiguous float32 for fast vector math)
    X_mat = np.ascontiguousarray(X_fit.to_numpy(dtype=np.float32))
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_mat)
    t_scale = time.perf_counter()

    # 5. Cluster Count & KMeans Fit (§1)
    optimal_k, clustering_method, sil_scores, fitted_models = select_optimal_k(
        X_scaled, n_samples=n_fit, random_state=random_state
    )

    # Retrieve pre-fit KMeans model (zero refitting overhead)
    final_kmeans = fitted_models.get(optimal_k)
    if final_kmeans is None:
        final_kmeans = KMeans(n_clusters=optimal_k, random_state=random_state, n_init=1, max_iter=8, tol=1e-2, algorithm="elkan")
        final_kmeans.fit(X_scaled)

    cluster_labels = final_kmeans.labels_
    t_kmeans = time.perf_counter()

    # 6. PCA (2D) Fit (§3)
    pca = PCA(n_components=2, random_state=random_state)
    pca_2d = pca.fit_transform(X_scaled)
    pca_x_all = pca_2d[:, 0]
    pca_y_all = pca_2d[:, 1]
    t_pca = time.perf_counter()

    # 7. Isolation Forest & Outlier Contamination (§2)
    if n_estimators_iso is None:
        n_estimators_iso = 10

    max_samples_iso = min(256, n_fit)
    iso = IsolationForest(
        n_estimators=n_estimators_iso,
        max_samples=max_samples_iso,
        contamination=FIXED_CONTAMINATION,
        random_state=random_state,
        n_jobs=1,
    )
    iso.fit(X_scaled)

    # Higher anomaly score = more anomalous
    raw_scores = iso.score_samples(X_scaled)
    anomaly_scores = -raw_scores
    is_outlier_all = iso.predict(X_scaled) == -1
    n_outliers = int(np.sum(is_outlier_all))
    t_iso = time.perf_counter()

    # Extract Top 100 Outlier Records (§2) using argpartition for O(N) selection
    if len(anomaly_scores) > MAX_OUTLIER_RECORDS:
        part_idx = np.argpartition(anomaly_scores, -MAX_OUTLIER_RECORDS)[-MAX_OUTLIER_RECORDS:]
        top_outlier_indices = part_idx[np.argsort(anomaly_scores[part_idx])[::-1]]
    else:
        top_outlier_indices = np.argsort(anomaly_scores)[::-1]

    outlier_records: List[Dict[str, Any]] = []

    for rank, idx in enumerate(top_outlier_indices):
        orig_row = context_fit.iloc[idx].to_dict()
        score = float(anomaly_scores[idx])

        # Resolve clean record ID
        rec_id: Any = None
        for id_candidate in ("id", "ID", "CustomerID", "customer_id", "client_id", "index"):
            if id_candidate in orig_row and pd.notna(orig_row[id_candidate]):
                rec_id = orig_row[id_candidate]
                break

        if rec_id is None:
            rec_id = int(idx)

        record: Dict[str, Any] = {
            "id": rec_id,
            "anomaly_score": round(score, 4),
            "cluster": int(cluster_labels[idx]),
        }

        # Include original features
        for k, v in orig_row.items():
            if k in record:
                continue
            if pd.isna(v):
                record[k] = None
            elif isinstance(v, (np.floating, float)):
                record[k] = round(float(v), 4)
            elif isinstance(v, (np.integer, int)):
                record[k] = int(v)
            elif isinstance(v, (pd.Timestamp, np.datetime64)):
                record[k] = str(v)
            else:
                record[k] = str(v)

        outlier_records.append(record)

    # 8. Scatter Payload Capping (§4)
    # Cap at 10,000 points maximum, ALWAYS preserving all flagged outliers
    if n_fit <= MAX_SCATTER_POINTS:
        selected_scatter_indices = np.arange(n_fit)
    else:
        outlier_idx_arr = np.where(is_outlier_all)[0]
        inlier_idx_arr = np.where(~is_outlier_all)[0]

        n_outliers_total = len(outlier_idx_arr)
        needed_inliers = max(0, MAX_SCATTER_POINTS - n_outliers_total)

        rng = np.random.default_rng(random_state)
        if len(inlier_idx_arr) > needed_inliers:
            sampled_inliers = rng.choice(inlier_idx_arr, size=needed_inliers, replace=False)
        else:
            sampled_inliers = inlier_idx_arr

        selected_scatter_indices = np.sort(
            np.concatenate([outlier_idx_arr, sampled_inliers])
        )

    # Coordinates for response (vectorized numpy conversions)
    final_pca_x = np.round(pca_x_all[selected_scatter_indices], 4).tolist()
    final_pca_y = np.round(pca_y_all[selected_scatter_indices], 4).tolist()
    final_clusters = cluster_labels[selected_scatter_indices].tolist()
    final_outlier_mask = is_outlier_all[selected_scatter_indices].tolist()

    points_list = [
        {"x": final_pca_x[i], "y": final_pca_y[i], "clusterId": final_clusters[i]}
        for i in range(len(selected_scatter_indices))
    ]

    t_end = time.perf_counter()
    compute_total_ms = round((t_end - t0) * 1000, 1)

    timing_ms = {
        "prepare_features": round((t_prep - t0) * 1000, 1),
        "scaling": round((t_scale - t_prep) * 1000, 1),
        "kmeans_clustering": round((t_kmeans - t_scale) * 1000, 1),
        "pca_projection": round((t_pca - t_kmeans) * 1000, 1),
        "isolation_forest": round((t_iso - t_pca) * 1000, 1),
        "payload_formatting": round((t_end - t_iso) * 1000, 1),
        "compute_total": compute_total_ms,
        "budget": 200.0,
        "within_budget": bool(compute_total_ms <= 200.0),
    }

    result: Dict[str, Any] = {
        "status": "ok",
        "message": (
            f"Segmentation complete with K={optimal_k} ({clustering_method}). "
            f"Flagged {n_outliers} anomalies at {FIXED_CONTAMINATION*100:.0f}% rate."
        ),
        "optimal_k": optimal_k,
        "clusterCount": optimal_k,
        "clustering_method": clustering_method,
        "pca_x": final_pca_x,
        "pca_y": final_pca_y,
        "cluster_assignments": final_clusters,
        "clusters": final_clusters,
        "points": points_list,
        "outlier_records": outlier_records,
        "outlier_mask": final_outlier_mask,
        "outlierMask": final_outlier_mask,
        "outlier_score_method": "isolation_forest",
        "outlierScoreMethod": "isolation_forest",
        "correlation_matrix": corr_matrix,
        "correlation_matrix_truncated": corr_truncated,
        "subsampled": subsampled,
        "original_row_count": n_samples_raw,
        "features_used": feature_names,
        "n_outliers": n_outliers,
        "contamination": FIXED_CONTAMINATION,
        "timing_ms": timing_ms,
        "silhouette_scores": sil_scores,
        "skew_transformed_columns": transformed_cols,
    }

    return result
