"""Agent 2 — Real-Dataset Validation Test Suite.

Validates end-to-end processing against real-world benchmark datasets:
1. day.csv:
   - Date format detected day-first
   - instant, casual, registered dropped when target=cnt
   - Forecast returns valid values
   - No leakage warnings triggered
2. airline-passengers.csv:
   - Monthly frequency detected
   - No day-based lags (7, 14, 21, 30) used
   - Short series (144 rows) handled cleanly
   - Seasonal-naive skill reported
3. online_retail.csv:
   - Passes the 50 MB upload gate
   - Loads with correct encoding (Latin-1 / ISO-8859-1)
   - Cancellations filtered
   - Daily net revenue series constructed
   - Cancellation count present in data_quality
   - End-to-end model compute under 200 ms (load/parse reported separately)
4. Wholesale_customers_data.csv:
   - No date column -> /forecast returns a clear non-error message (HTTP 200)
   - /hypotheses runs Welch's t-test (Channel, 2 groups) and One-Way ANOVA (Region, 3 groups)
   - Integer-coded Channel/Region detected as categorical candidates across spend columns
"""
from __future__ import annotations

import os
from pathlib import Path

import statistics
import threadpoolctl
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

DATASET_CANDIDATES = [
    Path(r"C:\Users\rfate\Desktop\report\project\Project - 2\Datasets\phase-3A"),
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


# ---------------------------------------------------------------------------
# 1. day.csv
# ---------------------------------------------------------------------------

@pytest.mark.latency
def test_day_csv_forecast_and_leakage_prevention():
    """day.csv: date format detected day-first; instant, casual, registered dropped when target=cnt;
    forecast returns; no leakage warning.
    """
    path = _get_dataset_path("day.csv")
    raw = path.read_bytes()

    # Direct feature pipeline inspection
    df = load_tabular(raw, "day.csv")
    prep = fp.prepare_series(df, target="cnt")

    # 1. Assert date format detected day-first
    assert prep.date_format == "day-first", f"Expected day-first format, got {prep.date_format}"

    # 2. Assert instant, casual, registered dropped when target=cnt
    dropped_names = set(prep.dropped.keys())
    assert "instant" in dropped_names, "instant must be dropped as ID"
    assert "casual" in dropped_names, "casual must be dropped as target component"
    assert "registered" in dropped_names, "registered must be dropped as target component"

    # Exogenous columns must not leak target components
    for dropped_col in ("casual", "registered", "instant"):
        assert not any(dropped_col in c.lower() for c in prep.exog.columns), (
            f"Exogenous features contain dropped column {dropped_col!r}"
        )

    # 3. No leakage warning in notes or preprocessing
    for note in prep.notes:
        assert "leakage" not in note.lower(), f"Unexpected leakage warning in notes: {note}"

    # 4. API endpoint verification: /api/v1/forecast returns valid predictions
    with threadpoolctl.threadpool_limits(limits=2):
        client.post(
            "/api/v1/forecast",
            files={"file": ("day.csv", raw)},
            data={"target": "cnt", "horizon": "14", "use_llm": "false"},
        )
        timings = []
        last_res = None
        for _ in range(5):
            r = client.post(
                "/api/v1/forecast",
                files={"file": ("day.csv", raw)},
                data={"target": "cnt", "horizon": "14", "use_llm": "false"},
            )
            assert r.status_code == 200
            res = r.json()
            last_res = res
            timings.append(res["timing_ms"]["compute_total"])
        med_compute = float(statistics.median(timings))

    assert last_res["status"] == "ok"
    assert last_res["dataset"]["date_format"] == "day-first"
    assert len(last_res["forecast"]["values"]) == 14
    assert len(last_res["forecast"]["dates"]) == 14
    assert all(v >= 0 for v in last_res["forecast"]["values"])
    assert med_compute < 500, f"Median compute {med_compute}ms exceeded 500ms budget: {timings}"


# ---------------------------------------------------------------------------
# 2. airline-passengers.csv
# ---------------------------------------------------------------------------

def test_airline_passengers_monthly_short_series_and_skill():
    """airline-passengers.csv: monthly frequency, no day-based lags (7/14/21/30) used;
    short series (144 rows) handled; seasonal-naive skill reported.
    """
    path = _get_dataset_path("airline-passengers.csv")
    raw = path.read_bytes()

    r = client.post(
        "/api/v1/forecast",
        files={"file": ("airline-passengers.csv", raw)},
        data={"horizon": "12", "use_llm": "false"},
    )
    assert r.status_code == 200
    res = r.json()

    # 1. Monthly frequency detected
    assert res["dataset"]["frequency"] == "monthly"

    # 2. No day-based lags (7/14/21/30) used
    lags = res["features"]["lags"]
    for day_lag in (7, 14, 21, 30):
        assert day_lag not in lags, f"Day-based lag {day_lag} improperly used in monthly series: {lags}"

    # Monthly lag (12) should be present
    assert 12 in lags, f"Expected seasonal lag 12 in monthly lags: {lags}"

    # 3. Short series (144 rows) handled
    assert res["dataset"]["n_periods"] == 144
    assert res["status"] == "ok"
    assert len(res["forecast"]["values"]) == 12

    # 4. Seasonal-naive skill reported
    assert res["skill_vs_seasonal_naive"] is not None
    assert isinstance(res["skill_vs_seasonal_naive"], (int, float))
    assert "seasonal_naive" in res["metrics"]
    assert res["metrics"]["seasonal_naive"]["rmse"] > 0


# ---------------------------------------------------------------------------
# 3. online_retail.csv
# ---------------------------------------------------------------------------

@pytest.mark.latency
def test_online_retail_50mb_encoding_filtering_and_compute():
    """online_retail.csv: passes the 50 MB gate; loads with correct encoding;
    cancellations filtered; daily net revenue series; cancellation count present in data_quality;
    end-to-end compute under 200 ms (report load/parse time separately from model compute).
    """
    path = _get_dataset_path("online_retail.csv")
    raw = path.read_bytes()

    # 1. Passes the 50 MB gate
    file_size = len(raw)
    max_50mb = 50 * 1024 * 1024
    assert file_size <= max_50mb, f"File size {file_size} exceeds 50 MB limit ({max_50mb})"

    # 2. Loads with correct encoding (Latin-1)
    df = load_tabular(raw, "online_retail.csv")
    assert len(df) == 541909, f"Expected 541909 rows, got {len(df)}"

    # 3. Aggregation to daily net revenue series
    prep = fp.prepare_series(df)
    assert prep.target == "net_revenue"
    assert prep.cfg.label == "D"

    # 4. Cancellations filtered & cancellation count present in data_quality
    dq = prep.data_quality
    assert "cancellation_rows_dropped" in dq, "cancellation_rows_dropped missing in data_quality"
    assert dq["cancellation_rows_dropped"] > 0, "No cancellations were dropped"
    assert "cancellation_invoices" in dq, "cancellation_invoices missing in data_quality"
    assert dq["cancellation_invoices"] > 0

    # 5. End-to-end model compute under 200 ms (load/parse reported separately)
    with threadpoolctl.threadpool_limits(limits=2):
        # Warm up first
        run_forecast(prep, horizon=14)
        engine_timings = []
        last_engine_res = None
        for _ in range(5):
            res = run_forecast(prep, horizon=14)
            last_engine_res = res
            engine_timings.append(res["timing_ms"]["compute_total"])
        med_engine_compute = float(statistics.median(engine_timings))

    assert last_engine_res["status"] == "ok"
    assert len(last_engine_res["forecast"]["values"]) == 14
    assert med_engine_compute < 200, (
        f"Model median compute {med_engine_compute}ms exceeded 200ms budget: {engine_timings}"
    )

    # API verification: load_parse is reported separately from compute_total
    with threadpoolctl.threadpool_limits(limits=2):
        client.post(
            "/api/v1/forecast",
            files={"file": ("online_retail.csv", raw)},
            data={"use_llm": "false"},
        )
        api_timings = []
        within_budgets = []
        last_api_res = None
        for _ in range(5):
            r = client.post(
                "/api/v1/forecast",
                files={"file": ("online_retail.csv", raw)},
                data={"use_llm": "false"},
            )
            assert r.status_code == 200
            api_res = r.json()
            last_api_res = api_res
            api_timings.append(api_res["timing_ms"]["compute_total"])
            within_budgets.append(api_res["timing_ms"]["within_budget"])
        med_api_compute = float(statistics.median(api_timings))

    assert last_api_res["status"] == "ok"
    tm = last_api_res["timing_ms"]
    assert "load_parse" in tm, "load_parse timing must be reported separately"
    assert "compute_total" in tm, "compute_total must be reported"
    assert med_api_compute < 200, f"API model median compute {med_api_compute}ms exceeded 200ms: {api_timings}"
    assert all(within_budgets), f"API within_budget failed: {api_timings}"
    assert tm["within_budget"] is True


# ---------------------------------------------------------------------------
# 4. Wholesale_customers_data.csv
# ---------------------------------------------------------------------------

def test_wholesale_customers_no_date_and_hypotheses():
    """Wholesale_customers_data.csv: no date column -> /forecast returns a clear non-error message;
    /hypotheses runs Welch (Channel, 2 groups) and ANOVA (Region, 3 groups) on spend columns;
    integer-coded Channel/Region detected as categorical.
    """
    path = _get_dataset_path("Wholesale customers data.csv", "Wholesale_customers_data.csv")
    raw = path.read_bytes()

    # 1. No date column -> /forecast returns a clear non-error message (HTTP 200, status="no_date_column")
    r_fc = client.post(
        "/api/v1/forecast",
        files={"file": ("Wholesale_customers_data.csv", raw)},
        data={"use_llm": "false"},
    )
    assert r_fc.status_code == 200, f"Expected 200 non-error response, got {r_fc.status_code}: {r_fc.text}"
    j_fc = r_fc.json()
    assert j_fc["status"] == "no_date_column"
    assert "message" in j_fc
    assert "date column" in j_fc["message"].lower()

    # 2. Integer-coded Channel and Region detected as categorical
    df = load_tabular(raw, "Wholesale_customers_data.csv")
    cats = fp.detect_categorical_candidates(df)
    assert "Channel" in cats, f"Channel not detected as categorical: {cats}"
    assert "Region" in cats, f"Region not detected as categorical: {cats}"

    # 3. /hypotheses runs Welch (Channel, 2 groups) and ANOVA (Region, 3 groups) on spend columns
    spend_columns = ["Fresh", "Milk", "Grocery", "Frozen", "Detergents_Paper", "Delicassen"]
    for spend_col in spend_columns:
        r_hyp = client.post(
            "/api/v1/hypotheses",
            files={"file": ("Wholesale_customers_data.csv", raw)},
            data={"target": spend_col, "use_llm": "false"},
        )
        assert r_hyp.status_code == 200
        j_hyp = r_hyp.json()
        assert j_hyp["status"] == "ok"

        tests_by_col = {t["grouping_column"]: t for t in j_hyp["tests"]}
        assert "Channel" in tests_by_col, f"Channel test missing for target {spend_col}"
        assert "Region" in tests_by_col, f"Region test missing for target {spend_col}"

        # Welch's t-test for Channel (2 groups)
        channel_test = tests_by_col["Channel"]
        assert channel_test["test"] == "welch_t"
        assert channel_test["n_groups"] == 2
        assert "statistic" in channel_test
        assert "p_value" in channel_test
        assert "lift_pct" in channel_test
        assert channel_test["effect_size"]["name"] == "cohens_d"

        # ANOVA for Region (3 groups)
        region_test = tests_by_col["Region"]
        assert region_test["test"] == "anova"
        assert region_test["n_groups"] == 3
        assert "statistic" in region_test
        assert "p_value" in region_test
        assert region_test["effect_size"]["name"] == "eta_squared"
