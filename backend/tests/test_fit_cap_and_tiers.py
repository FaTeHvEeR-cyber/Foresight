"""Tests for 10,000-row fit cap, full-table scoring, and tier-aware latency budget (WS-D)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analytics.outlier_engine import (
    FIT_CAP_ROWS,
    MAX_SCATTER_POINTS,
    run_segmentation,
)


def test_fit_cap_applied_only_when_n_over_10000():
    """Verify that fit cap subsampling fires if and only if N > 10,000 rows."""
    rng = np.random.default_rng(42)

    # 1. Exactly 10,000 rows -> NOT subsampled
    df_10k = pd.DataFrame(
        rng.normal(0, 1, (10_000, 4)),
        columns=[f"col_{i}" for i in range(4)],
    )
    res_10k = run_segmentation(df_10k, random_state=42)
    assert res_10k["status"] == "ok"
    assert res_10k["subsampled"] is False, "10,000 rows should NOT trigger fit-cap subsampling"
    assert res_10k["original_row_count"] == 10_000
    assert len(res_10k["pca_x"]) == 10_000

    # 2. 10,001 rows -> fit-cap subsampling triggers
    df_10001 = pd.DataFrame(
        rng.normal(0, 1, (10_001, 4)),
        columns=[f"col_{i}" for i in range(4)],
    )
    res_10001 = run_segmentation(df_10001, random_state=42)
    assert res_10001["status"] == "ok"
    assert res_10001["subsampled"] is True, "10,001 rows MUST trigger fit-cap subsampling"
    assert res_10001["original_row_count"] == 10_001
    assert len(res_10001["pca_x"]) == MAX_SCATTER_POINTS


def test_scoring_covers_all_n_rows():
    """Verify that even when fit is capped at 10,000 rows, ALL N rows are scored.

    An extreme anomaly placed well past index 10,000 (e.g. index 11,500)
    must still be scored, flagged, and returned in outlier_records.
    """
    rng = np.random.default_rng(42)
    total_rows = 12_500
    data = rng.normal(0, 1, (total_rows, 4))

    # Plant an unmistakable anomaly at row index 11,500
    target_outlier_idx = 11_500
    data[target_outlier_idx, :] = [9999.0, -9999.0, 9999.0, -9999.0]

    df = pd.DataFrame(data, columns=[f"col_{i}" for i in range(4)])
    df["id"] = np.arange(total_rows)

    res = run_segmentation(df, random_state=42)
    assert res["status"] == "ok"
    assert res["subsampled"] is True
    assert res["original_row_count"] == total_rows

    # Top outlier in outlier_records must be our planted outlier from row 11,500
    outlier_ids = [r["id"] for r in res["outlier_records"]]
    assert outlier_ids[0] == target_outlier_idx, (
        f"Row {target_outlier_idx} beyond fit-cap was not ranked as top outlier: got {outlier_ids[:5]}"
    )


def test_fit_cap_reproducibility():
    """Verify that the random sample, K selection, and outlier count are 100% reproducible."""
    rng = np.random.default_rng(42)
    df = pd.DataFrame(
        rng.normal(0, 1, (15_000, 4)),
        columns=[f"col_{i}" for i in range(4)],
    )

    res1 = run_segmentation(df, random_state=42)
    res2 = run_segmentation(df, random_state=42)

    assert res1["optimal_k"] == res2["optimal_k"]
    assert res1["clustering_method"] == res2["clustering_method"]
    assert res1["n_outliers"] == res2["n_outliers"]
    assert res1["pca_x"] == res2["pca_x"]
    assert res1["pca_y"] == res2["pca_y"]
    assert res1["cluster_assignments"] == res2["cluster_assignments"]
    assert [r["id"] for r in res1["outlier_records"]] == [r["id"] for r in res2["outlier_records"]]


@pytest.mark.parametrize(
    "n_rows,expected_budget,expected_tier",
    [
        (5_000, 200.0, "strict_200"),
        (5_001, 500.0, "relaxed_500"),
        (20_000, 500.0, "relaxed_500"),
        (20_001, 500.0, "best_effort"),
    ],
)
def test_budget_tiers_at_boundary_points(n_rows: int, expected_budget: float, expected_tier: str):
    """Verify budget and budget_tier transition exactly at N=5,000, 5,001, 20,000, and 20,001."""
    rng = np.random.default_rng(42)
    df = pd.DataFrame(
        rng.normal(0, 1, (n_rows, 3)),
        columns=["a", "b", "c"],
    )

    res = run_segmentation(df, random_state=42)
    assert res["status"] == "ok"
    tm = res["timing_ms"]

    assert tm["budget"] == expected_budget
    assert tm["budget_tier"] == expected_tier
    assert tm["within_budget"] == (tm["compute_total"] <= expected_budget)
