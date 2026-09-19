"""Real data validation tests for Phase 3A: Forecasting & Hypothesis Engine.

Executes end-to-end against real-world benchmark datasets:
1. Airline Passengers (144 monthly observations, Box-Jenkins)
2. Bike Sharing (day.csv, 730 daily observations)
3. Wholesale Customers (440 commercial clients, Channel/Region expenditure)
4. Online Retail (541k transaction rows, Latin-1, ~50MB transaction log)
5. Rossmann Store Sales (benchmark_data.parquet, promo lift verification)
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app
from src.analytics import feature_pipeline as fp
from src.analytics.forecast_engine import run_forecast
from src.analytics.hypothesis_engine import run_hypotheses
from src.analytics.loader import load_tabular

client = TestClient(app)

# Real data search paths
DATASET_CANDIDATES = [
    Path(r"C:\Users\rfate\Desktop\report\project\Project - 2\Datasets\phase-3A"),
    Path(__file__).resolve().parent.parent / "data",
    Path(__file__).resolve().parent.parent.parent / "data",
]


def _get_dataset_path(filename: str) -> Path:
    for base in DATASET_CANDIDATES:
        p = base / filename
        if p.exists():
            return p
    pytest.skip(f"Benchmark dataset {filename!r} not found in candidate paths.")


# ---------------------------------------------------------------------------
# 1. Real Airline Passengers Dataset (Monthly Series)
# ---------------------------------------------------------------------------

def test_real_airline_passengers_validation():
    path = _get_dataset_path("airline-passengers.csv")
    df = pd.read_csv(path)

    prep = fp.prepare_series(df)
    assert prep.cfg.label == "M", f"Expected monthly frequency 'M', got {prep.cfg.label}"
    assert prep.target in ("total_passengers", "#Passengers")
    assert len(prep.y) == 144

    # Lags check: monthly series should have seasonal lag 12, no daily lag 7
    lags, wins, holdout = fp.select_lags(prep.cfg, len(prep.y))
    assert 12 in lags
    assert 7 not in lags

    # Forecast execution (with warm-up)
    run_forecast(prep)
    res = run_forecast(prep, horizon=12)
    assert res["status"] == "ok"
    assert len(res["forecast"]["dates"]) == 12
    assert len(res["forecast"]["values"]) == 12
    assert all(v > 0 for v in res["forecast"]["values"]), "Airline passenger forecasts must be positive"
    assert all(v >= 0 for v in res["forecast"]["lower"]), "Lower confidence bound must be non-negative"
    assert res["selected_model"] in ("ridge", "xgboost")
    assert res["timing_ms"]["compute_total"] < 200, f"Compute exceeded budget: {res['timing_ms']}"


# ---------------------------------------------------------------------------
# 2. Real Bike Sharing Dataset (Daily Series & Leakage Prevention)
# ---------------------------------------------------------------------------

def test_real_bike_sharing_validation():
    path = _get_dataset_path("day.csv")
    df = pd.read_csv(path)

    prep = fp.prepare_series(df, target="cnt")
    assert prep.cfg.label == "D", f"Expected daily frequency 'D', got {prep.cfg.label}"
    assert len(prep.y) == 730

    # Leakage defense: instant dropped as ID, casual + registered dropped as additive components
    dropped_cols = set(prep.dropped.keys())
    assert "instant" in dropped_cols, "instant should be dropped as ID"
    assert "casual" in dropped_cols, "casual should be dropped as target component"
    assert "registered" in dropped_cols, "registered should be dropped as target component"

    # Ensure exogenous columns do not contain the dropped columns
    assert not any("casual" in c or "registered" in c for c in prep.exog.columns)

    # Forecast execution (with warm-up)
    run_forecast(prep)
    res = run_forecast(prep, horizon=14)
    assert res["status"] == "ok"
    assert len(res["forecast"]["dates"]) == 14
    assert res["selected_model"] in ("ridge", "xgboost")
    # Holdout R2 should show genuine predictive capability
    sel = res["selected_model"]
    assert res["metrics"][sel]["r2"] is not None
    assert res["timing_ms"]["compute_total"] < 500, f"Compute took {res['timing_ms']['compute_total']}ms"


# ---------------------------------------------------------------------------
# 3. Real Wholesale Customers Dataset (Parametric & Non-Parametric Hypotheses)
# ---------------------------------------------------------------------------

def test_real_wholesale_customers_hypotheses():
    path = _get_dataset_path("Wholesale customers data.csv")
    df = pd.read_csv(path)

    res = run_hypotheses(df, target="Fresh")
    assert res["status"] == "ok"
    assert len(res["tests"]) >= 2

    test_by_col = {t["grouping_column"]: t for t in res["tests"]}
    assert "Channel" in test_by_col
    assert "Region" in test_by_col

    # Channel has 2 groups -> Welch's t-test
    channel_test = test_by_col["Channel"]
    assert channel_test["test"] == "welch_t"
    assert "lift_pct" in channel_test
    assert channel_test["effect_size"]["name"] == "cohens_d"
    assert "nonparametric_p" in channel_test
    assert "p_value_adjusted" in channel_test

    # Region has 3 groups -> One-Way ANOVA
    region_test = test_by_col["Region"]
    assert region_test["test"] == "anova"
    assert region_test["effect_size"]["name"] == "eta_squared"
    assert "nonparametric_p" in region_test
    assert "p_value_adjusted" in region_test

    # Timing
    assert res["timing_ms"]["compute_total"] < 100, f"Hypotheses took {res['timing_ms']['compute_total']}ms"


# ---------------------------------------------------------------------------
# 4. Real UCI Online Retail Dataset (541k Transaction Aggregation & Forecast)
# ---------------------------------------------------------------------------

def test_real_online_retail_pipeline():
    path = _get_dataset_path("online_retail.csv")
    if not path.exists():
        pytest.skip("online_retail.csv not present")

    # Verify loading raw bytes through loader with Latin-1 auto-detection
    raw = path.read_bytes()
    df = load_tabular(raw, "online_retail.csv")
    assert len(df) == 541909

    # Transaction log detection & aggregation
    assert fp.is_retail_transactions(df)
    prep = fp.prepare_series(df)
    assert prep.target == "net_revenue"
    assert prep.cfg.label == "D"
    assert prep.data_quality["rows_in"] == 541909
    assert prep.data_quality["cancellation_rows_dropped"] > 0
    assert prep.data_quality["zero_or_negative_price_rows_dropped"] > 0
    assert prep.data_quality["gaps_filled"] > 0  # non-trading Saturdays filled with zero revenue
    assert (prep.y >= 0).all()

    # Fast forecast run on aggregated daily net revenue
    res = run_forecast(prep, horizon=14)
    assert res["status"] == "ok"
    assert len(res["forecast"]["values"]) == 14
    assert res["selected_model"] in ("ridge", "xgboost")
    del df, raw, prep, res
    import gc
    gc.collect()


# ---------------------------------------------------------------------------
# 5. Real Rossmann Benchmark Store Sales Promo Lift Verification
# ---------------------------------------------------------------------------

def test_real_benchmark_promo_lift():
    benchmark_path = Path(__file__).resolve().parent.parent / "data" / "benchmark_data.parquet"
    if not benchmark_path.exists():
        pytest.skip("benchmark_data.parquet not present in backend/data")

    df = pd.read_parquet(benchmark_path)
    assert "promo_flag" in df.columns
    assert "units_sold" in df.columns

    res = run_hypotheses(df, target="units_sold", group_cols=["promo_flag"])
    assert res["status"] == "ok"
    t = res["tests"][0]
    assert t["test"] == "welch_t"
    assert t["significant"] is True
    assert t["lift_pct"] > 0, "Promotional periods should produce positive sales lift"
    assert t["p_value"] < 0.01


# ---------------------------------------------------------------------------
# 6. REST API Endpoints with Real Payloads
# ---------------------------------------------------------------------------

def test_api_real_bike_forecast():
    path = _get_dataset_path("day.csv")
    raw = path.read_bytes()

    # Warm-up request
    client.post(
        "/api/v1/forecast",
        files={"file": ("day.csv", raw)},
        data={"target": "cnt", "horizon": "14", "use_llm": "false"},
    )
    r = client.post(
        "/api/v1/forecast",
        files={"file": ("day.csv", raw)},
        data={"target": "cnt", "horizon": "14", "use_llm": "false"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok"
    assert j["dataset"]["frequency"] == "daily"
    assert len(j["forecast"]["values"]) == 14
    assert j["recommended_visualization"]["chart"] == "line_chart"
    assert j["timing_ms"]["within_budget"] is True


def test_api_real_wholesale_hypotheses():
    path = _get_dataset_path("Wholesale customers data.csv")
    raw = path.read_bytes()

    r = client.post(
        "/api/v1/hypotheses",
        files={"file": ("wholesale.csv", raw)},
        data={"target": "Milk", "use_llm": "false"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok"
    assert len(j["tests"]) >= 2
    assert j["recommended_visualization"]["chart"] == "bar_comparison"
