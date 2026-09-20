"""Rossmann Benchmark Parity Verification Test Suite (Phase 3A vs Phase 2.5).

Verifies the Agent 3 exit criteria:
1. Confirm the shared feature_pipeline.py is the module the Phase 2.5 offline scripts import.
2. Confirm the locked Phase 2.5 offline training results remain reproducible.
3. Run per-request forecasting on a handful of Rossmann stores (daily sales, Open==1 evaluation, ~6-week holdout)
   and verify store-level RMSPE satisfies the proposed parity bar (no worse than the Phase 2.5 Ridge gate: 20%).
4. Reproduce the promo Welch t-test through hypothesis engine; Phase 2.5 reference is 38.7% promo lift, p ~ 0.
   Asserts lift does not differ by more than 2 percentage points.
5. Verify REST API /api/v1/hypotheses endpoint parity.
6. Verify delivery of backend/reports/phase3a_rossmann_parity.md.
"""
from __future__ import annotations

import importlib
import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app
from src.analytics import feature_pipeline as fp
from src.analytics.forecast_engine import run_forecast
from src.analytics.hypothesis_engine import run_hypotheses
from scripts.rossmann_parity_3a import (
    PHASE2_5_PROMO_LIFT_REF,
    PHASE2_5_PROMO_LIFT_TOL,
    PHASE2_5_RIDGE_GATE_RMSPE,
    resolve_rossmann_dataset,
    run_promo_welch_t_test,
    run_store_forecasts,
    verify_feature_pipeline_sharing,
)

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Feature Pipeline Shared Module Verification
# ---------------------------------------------------------------------------

def test_feature_pipeline_shared_import():
    """Exit Criterion 1: Confirm shared feature_pipeline.py is imported by Phase 2.5 offline scripts."""
    tea_mod = importlib.import_module("src.training.train_engine_a")

    # Verify functions are identical references
    assert hasattr(tea_mod, "engineer_features"), "train_engine_a missing engineer_features"
    assert hasattr(fp, "engineer_features"), "feature_pipeline missing engineer_features"
    assert tea_mod.engineer_features is fp.engineer_features, (
        "train_engine_a.engineer_features must be imported directly from src.analytics.feature_pipeline"
    )

    assert hasattr(tea_mod, "compute_rmspe"), "train_engine_a missing compute_rmspe"
    assert hasattr(fp, "compute_rmspe"), "feature_pipeline missing compute_rmspe"
    assert tea_mod.compute_rmspe is fp.compute_rmspe, (
        "train_engine_a.compute_rmspe must be imported directly from src.analytics.feature_pipeline"
    )

    # Check verification helper
    sharing_check = verify_feature_pipeline_sharing()
    assert sharing_check["shared_feature_pipeline_confirmed"] is True


# ---------------------------------------------------------------------------
# 2. Phase 2.5 Offline Results Reproducibility
# ---------------------------------------------------------------------------

def test_phase2_5_results_reproducible(tmp_path):
    """Exit Criterion 2: Confirm locked Phase 2.5 results remain reproducible after refactoring."""
    tea_mod = importlib.import_module("src.training.train_engine_a")
    train_fn = tea_mod.train_engine_a

    res = train_fn(
        models_dir=tmp_path / "models",
        enforce_thresholds=False,
        random_state=42,
    )

    stats = res["exclusion_stats"]
    # Verify locked row counts
    assert stats["total_val_rows"] == 900
    assert stats["excluded_rows"] == 48
    assert stats["clean_val_rows"] == 852
    assert np.isclose(stats["excluded_pct"], 5.333333333, atol=0.01)

    # Verify training row counts
    assert len(res["train_df"]) == 3600

    # Verify model performance hierarchy: XGBoost beats Ridge
    metrics = res["metrics"]
    assert metrics["xgboost"]["rmspe"] < metrics["ridge"]["rmspe"], (
        f"XGBoost RMSPE ({metrics['xgboost']['rmspe']:.2f}%) must be lower than Ridge ({metrics['ridge']['rmspe']:.2f}%)"
    )
    assert metrics["xgboost"]["r2"] >= 0.85, f"XGBoost R2 below 0.85: {metrics['xgboost']['r2']:.4f}"


# ---------------------------------------------------------------------------
# 3. Promo Welch t-Test Parity (38.7% lift, p ~ 0)
# ---------------------------------------------------------------------------

def test_rossmann_promo_welch_t_test_parity():
    """Exit Criterion 3: Reproduce promo Welch t-test; Phase 2.5 reference is 38.7% promo lift, p~0.

    Flag if the lift differs by more than ~2 points.
    """
    try:
        data_path = resolve_rossmann_dataset()
    except FileNotFoundError:
        pytest.skip("Rossmann dataset not available in local candidate paths.")

    df = pd.read_csv(data_path, low_memory=False)
    promo_info = run_promo_welch_t_test(df)

    # Assert test properties
    assert promo_info["test_name"] == "welch_t"
    assert promo_info["significant"] is True
    assert promo_info["p_value"] < 0.01, f"Expected p < 0.01, got {promo_info['p_value']}"

    # Parity check against 38.7% reference with +/- 2.0% tolerance
    lift_diff = promo_info["diff_from_ref"]
    assert lift_diff <= PHASE2_5_PROMO_LIFT_TOL, (
        f"Promo lift ({promo_info['lift_pct']:.2f}%) differs from Phase 2.5 reference "
        f"({PHASE2_5_PROMO_LIFT_REF:.2f}%) by {lift_diff:.2f}% points (tolerance: <= {PHASE2_5_PROMO_LIFT_TOL:.2f}%)."
    )
    assert promo_info["lift_matches_parity"] is True


# ---------------------------------------------------------------------------
# 4. Store-Level Per-Request Forecasting Parity Bar (RMSPE <= 20%)
# ---------------------------------------------------------------------------

def test_rossmann_per_request_store_forecast_parity():
    """Exit Criterion 4: Per-request XGBoost store-level RMSPE no worse than the Phase 2.5 Ridge gate (20%)."""
    try:
        data_path = resolve_rossmann_dataset()
    except FileNotFoundError:
        pytest.skip("Rossmann dataset not available in local candidate paths.")

    df = pd.read_csv(data_path, low_memory=False)
    target_stores = [1, 2, 3, 4, 5]
    store_results = run_store_forecasts(df, target_stores, eval_open_only=True)

    assert len(store_results) == 5, f"Expected 5 store evaluations, got {len(store_results)}"

    for r in store_results:
        sid = r["store_id"]
        xgb_rmspe = r["xgb_rmspe_pct"]
        ridge_rmspe = r["ridge_rmspe_pct"]

        # Validate metrics are finite and positive
        assert xgb_rmspe is not None and np.isfinite(xgb_rmspe) and xgb_rmspe > 0
        assert ridge_rmspe is not None and np.isfinite(ridge_rmspe) and ridge_rmspe > 0
        assert r["xgb_r2"] is not None and np.isfinite(r["xgb_r2"])
        assert r["ridge_r2"] is not None and np.isfinite(r["ridge_r2"])

        # Parity bar assertion: XGBoost store RMSPE <= 20.0% (Phase 2.5 Ridge gate)
        assert r["xgb_meets_bar"] is True, (
            f"Store {sid} XGBoost RMSPE ({xgb_rmspe:.2f}%) exceeds the Phase 2.5 Ridge gate "
            f"({PHASE2_5_RIDGE_GATE_RMSPE:.1f}%)."
        )

        # In per-request Open==1 forecasting, XGBoost outperforms Ridge
        assert xgb_rmspe < ridge_rmspe, (
            f"Store {sid}: expected XGBoost RMSPE ({xgb_rmspe:.2f}%) < Ridge RMSPE ({ridge_rmspe:.2f}%)"
        )
        assert r["selected_model"] == "xgboost"

    # Average store RMSPE should be comfortably under 15%
    avg_xgb = float(np.mean([r["xgb_rmspe_pct"] for r in store_results]))
    assert avg_xgb < 15.0, f"Average store XGBoost RMSPE ({avg_xgb:.2f}%) should be < 15%"


# ---------------------------------------------------------------------------
# 5. REST API /api/v1/hypotheses Parity with Rossmann Data
# ---------------------------------------------------------------------------

def test_rossmann_hypotheses_api_endpoint():
    """Exit Criterion 5: Verify REST API /api/v1/hypotheses reproduces Welch t-test on Rossmann slice."""
    try:
        data_path = resolve_rossmann_dataset()
    except FileNotFoundError:
        pytest.skip("Rossmann dataset not available in local candidate paths.")

    # Use a representative sample of 2,000 Open==1 records from Rossmann (both Promo=0 and Promo=1)
    df = pd.read_csv(data_path, low_memory=False)
    sample_df = df[df["Open"] == 1][["Sales", "Promo"]].sample(2000, random_state=42).copy()

    csv_buf = io.StringIO()
    sample_df.to_csv(csv_buf, index=False)
    csv_bytes = csv_buf.getvalue().encode("utf-8")

    res = client.post(
        "/api/v1/hypotheses",
        files={"file": ("rossmann_sample.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"target": "Sales", "group_cols": "Promo", "use_llm": "false"},
    )
    assert res.status_code == 200, f"API returned {res.status_code}: {res.text}"
    j = res.json()
    assert j["status"] == "ok"
    assert len(j["tests"]) >= 1

    t = j["tests"][0]
    assert t["test"] == "welch_t"
    assert t["significant"] is True
    assert t["lift_pct"] > 0, "Promotional lift must be positive"
    assert t["p_value"] < 0.01


# ---------------------------------------------------------------------------
# 6. Deliverable Parity Report Verification
# ---------------------------------------------------------------------------

def test_parity_report_generated():
    """Exit Criterion 6: Verify backend/reports/phase3a_rossmann_parity.md exists and contains required sections."""
    report_file = Path(__file__).resolve().parent.parent / "reports" / "phase3a_rossmann_parity.md"
    assert report_file.is_file(), f"Parity report missing at: {report_file}"

    content = report_file.read_text(encoding="utf-8")
    assert "# Phase 3A Rossmann Benchmark Parity Report" in content
    assert "Parity Summary Table" in content
    assert "38.70%" in content
    assert "20.00%" in content
    assert "11.90%" in content
    assert "Global Model vs Per-Request Model" in content
    assert "Feature Pipeline Single-Source-of-Truth" in content
