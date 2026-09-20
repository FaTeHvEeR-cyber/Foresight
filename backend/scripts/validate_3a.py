"""Phase 3A Real-Dataset Validation & Latency Benchmarking Script.

Runs real benchmark datasets against /forecast and /hypotheses endpoints,
asserts data hygiene and behavioral contracts, measures p50/p95 latency over 20 runs each,
and writes comprehensive results to backend/reports/phase3a_validation.json.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

# Ensure backend root is in sys.path
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from src.analytics import feature_pipeline as fp
from src.analytics.forecast_engine import run_forecast
from src.analytics.hypothesis_engine import run_hypotheses
from src.analytics.loader import load_tabular

client = TestClient(app)

DATASET_CANDIDATES = [
    Path(r"C:\Users\rfate\Desktop\report\project\Project - 2\Datasets\phase-3A"),
    BACKEND_DIR / "data",
    BACKEND_DIR.parent / "data",
]


def find_dataset(*filenames: str) -> Path:
    for base in DATASET_CANDIDATES:
        for fname in filenames:
            p = base / fname
            if p.exists():
                return p
    raise FileNotFoundError(f"Could not find any of {filenames} in {DATASET_CANDIDATES}")


def calculate_latency_stats(timings: List[float]) -> Dict[str, Any]:
    arr = np.array(timings, dtype=float)
    return {
        "runs": len(timings),
        "p50_ms": round(float(np.percentile(arr, 50)), 2),
        "p95_ms": round(float(np.percentile(arr, 95)), 2),
        "mean_ms": round(float(np.mean(arr)), 2),
        "min_ms": round(float(np.min(arr)), 2),
        "max_ms": round(float(np.max(arr)), 2),
        "raw_ms": [round(t, 2) for t in timings],
    }


def validate_day_csv(path: Path) -> Dict[str, Any]:
    print("\n[1/4] Validating day.csv...")
    raw = path.read_bytes()
    df = load_tabular(raw, "day.csv")
    prep = fp.prepare_series(df, target="cnt")

    # 1. Date format detected day-first
    assert prep.date_format == "day-first", f"Expected day-first format, got {prep.date_format}"

    # 2. instant, casual, registered dropped when target=cnt
    dropped_keys = set(prep.dropped.keys())
    assert "instant" in dropped_keys, "instant not dropped as ID"
    assert "casual" in dropped_keys, "casual not dropped as target component"
    assert "registered" in dropped_keys, "registered not dropped as target component"
    for col in ("casual", "registered", "instant"):
        assert not any(col in c.lower() for c in prep.exog.columns), f"{col} leaked into exog"

    # 3. No leakage warning
    for note in prep.notes:
        assert "leakage" not in note.lower(), f"Leakage warning found in notes: {note}"

    # 4. Forecast returns valid output
    r = client.post(
        "/api/v1/forecast",
        files={"file": ("day.csv", raw)},
        data={"target": "cnt", "horizon": "14", "use_llm": "false"},
    )
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
    j = r.json()
    assert j["status"] == "ok"
    assert len(j["forecast"]["values"]) == 14

    # 20 Latency benchmark runs
    print("  Measuring latency over 20 runs...")
    timings = []
    compute_timings = []
    for _ in range(20):
        t0 = time.perf_counter()
        resp = client.post(
            "/api/v1/forecast",
            files={"file": ("day.csv", raw)},
            data={"target": "cnt", "horizon": "14", "use_llm": "false"},
        )
        elapsed = (time.perf_counter() - t0) * 1000
        timings.append(elapsed)
        compute_timings.append(resp.json()["timing_ms"]["compute_total"])

    stats = calculate_latency_stats(timings)
    compute_stats = calculate_latency_stats(compute_timings)
    print(f"  Passed! API p50: {stats['p50_ms']}ms, p95: {stats['p95_ms']}ms | Compute p50: {compute_stats['p50_ms']}ms, p95: {compute_stats['p95_ms']}ms")

    return {
        "status": "PASSED",
        "file": "day.csv",
        "assertions": {
            "date_format_detected_day_first": True,
            "instant_dropped_as_id": True,
            "casual_registered_dropped_leakage_prevented": True,
            "forecast_returns_valid": True,
            "no_leakage_warning": True,
        },
        "details": {
            "date_format": prep.date_format,
            "dropped_columns": prep.dropped,
            "forecast_horizon": 14,
            "selected_model": j["selected_model"],
        },
        "latency": {
            "api_endpoint": stats,
            "model_compute": compute_stats,
        },
    }


def validate_airline_passengers(path: Path) -> Dict[str, Any]:
    print("\n[2/4] Validating airline-passengers.csv...")
    raw = path.read_bytes()

    # Initial API test
    r = client.post(
        "/api/v1/forecast",
        files={"file": ("airline-passengers.csv", raw)},
        data={"horizon": "12", "use_llm": "false"},
    )
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
    j = r.json()

    # 1. Monthly frequency
    assert j["dataset"]["frequency"] == "monthly", f"Expected monthly frequency, got {j['dataset']['frequency']}"

    # 2. No day-based lags (7/14/21/30) used
    lags = j["features"]["lags"]
    for day_lag in (7, 14, 21, 30):
        assert day_lag not in lags, f"Day lag {day_lag} improperly used in monthly series: {lags}"
    assert 12 in lags, f"Seasonal monthly lag 12 missing: {lags}"

    # 3. Short series (144 rows) handled
    assert j["dataset"]["n_periods"] == 144
    assert j["status"] == "ok"
    assert len(j["forecast"]["values"]) == 12

    # 4. Seasonal-naive skill reported
    skill = j["skill_vs_seasonal_naive"]
    assert skill is not None, "skill_vs_seasonal_naive not reported"
    assert isinstance(skill, (int, float))

    # 20 Latency benchmark runs
    print("  Measuring latency over 20 runs...")
    timings = []
    compute_timings = []
    for _ in range(20):
        t0 = time.perf_counter()
        resp = client.post(
            "/api/v1/forecast",
            files={"file": ("airline-passengers.csv", raw)},
            data={"horizon": "12", "use_llm": "false"},
        )
        elapsed = (time.perf_counter() - t0) * 1000
        timings.append(elapsed)
        compute_timings.append(resp.json()["timing_ms"]["compute_total"])

    stats = calculate_latency_stats(timings)
    compute_stats = calculate_latency_stats(compute_timings)
    print(f"  Passed! API p50: {stats['p50_ms']}ms, p95: {stats['p95_ms']}ms | Compute p50: {compute_stats['p50_ms']}ms, p95: {compute_stats['p95_ms']}ms")

    return {
        "status": "PASSED",
        "file": "airline-passengers.csv",
        "assertions": {
            "monthly_frequency_detected": True,
            "no_day_based_lags_used": True,
            "short_series_144_rows_handled": True,
            "seasonal_naive_skill_reported": True,
        },
        "details": {
            "frequency": j["dataset"]["frequency"],
            "n_periods": j["dataset"]["n_periods"],
            "lags": lags,
            "skill_vs_seasonal_naive": skill,
            "selected_model": j["selected_model"],
        },
        "latency": {
            "api_endpoint": stats,
            "model_compute": compute_stats,
        },
    }


def validate_online_retail(path: Path) -> Dict[str, Any]:
    print("\n[3/4] Validating online_retail.csv...")
    raw = path.read_bytes()

    # 1. Passes 50 MB gate
    file_size = len(raw)
    max_50mb = 50 * 1024 * 1024
    assert file_size <= max_50mb, f"File size {file_size} exceeds 50 MB gate ({max_50mb})"

    # 2. Loads with correct encoding (Latin-1)
    t_load0 = time.perf_counter()
    df = load_tabular(raw, "online_retail.csv")
    load_parse_duration_ms = round((time.perf_counter() - t_load0) * 1000, 2)
    assert len(df) == 541909, f"Expected 541909 rows, got {len(df)}"

    # 3. Aggregation & Cancellations filtered
    prep = fp.prepare_series(df)
    assert prep.target == "net_revenue", f"Expected net_revenue target, got {prep.target}"
    assert prep.cfg.label == "D", f"Expected daily frequency, got {prep.cfg.label}"

    # 4. Cancellation count present in data_quality
    dq = prep.data_quality
    assert "cancellation_rows_dropped" in dq
    assert dq["cancellation_rows_dropped"] > 0
    assert "cancellation_invoices" in dq
    assert dq["cancellation_invoices"] > 0

    # 5. Model compute latency under 200 ms (measured over 20 runs)
    print("  Measuring model compute latency over 20 runs...")
    compute_timings = []
    for _ in range(20):
        res = run_forecast(prep, horizon=14)
        compute_timings.append(res["timing_ms"]["compute_total"])

    compute_stats = calculate_latency_stats(compute_timings)
    assert compute_stats["p95_ms"] < 200, f"Model compute p95 {compute_stats['p95_ms']}ms exceeded 200ms budget"

    # Also run API request to verify separate timing reporting
    r_api = client.post(
        "/api/v1/forecast",
        files={"file": ("online_retail.csv", raw)},
        data={"use_llm": "false"},
    )
    assert r_api.status_code == 200
    j_api = r_api.json()
    assert "load_parse" in j_api["timing_ms"], "load_parse must be reported separately"
    assert "compute_total" in j_api["timing_ms"], "compute_total must be reported"
    assert j_api["timing_ms"]["compute_total"] < 200, f"Compute exceeded 200ms: {j_api['timing_ms']}"

    print(f"  Passed! Load/parse: {j_api['timing_ms']['load_parse']}ms (reported separately) | Compute p50: {compute_stats['p50_ms']}ms, p95: {compute_stats['p95_ms']}ms (< 200ms budget)")

    return {
        "status": "PASSED",
        "file": "online_retail.csv",
        "assertions": {
            "passes_50mb_gate": True,
            "loads_with_correct_encoding_latin1": True,
            "cancellations_filtered": True,
            "daily_net_revenue_series": True,
            "cancellation_count_in_data_quality": True,
            "end_to_end_compute_under_200ms": True,
        },
        "details": {
            "file_size_bytes": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "rows_in": dq["rows_in"],
            "cancellation_rows_dropped": dq["cancellation_rows_dropped"],
            "cancellation_invoices": dq["cancellation_invoices"],
            "target": prep.target,
            "frequency": prep.cfg.name,
            "load_parse_duration_ms": load_parse_duration_ms,
            "api_timing_ms": j_api["timing_ms"],
        },
        "latency": {
            "model_compute_20_runs": compute_stats,
            "load_parse_ms_reported_separately": j_api["timing_ms"]["load_parse"],
            "prepare_series_ms": j_api["timing_ms"]["prepare_series"],
        },
    }


def validate_wholesale_customers(path: Path) -> Dict[str, Any]:
    print("\n[4/4] Validating Wholesale_customers_data.csv...")
    raw = path.read_bytes()

    # 1. No date column -> /forecast returns a clear non-error message (HTTP 200)
    print("  Testing /forecast response without date column over 20 runs...")
    fc_timings = []
    for _ in range(20):
        t0 = time.perf_counter()
        r_fc = client.post(
            "/api/v1/forecast",
            files={"file": ("Wholesale_customers_data.csv", raw)},
            data={"use_llm": "false"},
        )
        elapsed = (time.perf_counter() - t0) * 1000
        fc_timings.append(elapsed)
        assert r_fc.status_code == 200, f"Expected 200 non-error response, got {r_fc.status_code}: {r_fc.text}"
        j_fc = r_fc.json()
        assert j_fc["status"] == "no_date_column"
        assert "date column" in j_fc["message"].lower()

    fc_stats = calculate_latency_stats(fc_timings)

    # 2. Integer-coded Channel/Region detected as categorical
    df = load_tabular(raw, "Wholesale_customers_data.csv")
    cats = fp.detect_categorical_candidates(df)
    assert "Channel" in cats, f"Channel not detected as categorical: {cats}"
    assert "Region" in cats, f"Region not detected as categorical: {cats}"

    # 3. /hypotheses runs Welch (Channel, 2 groups) and ANOVA (Region, 3 groups) on spend columns
    print("  Testing /hypotheses spend columns (Fresh, Milk, Grocery, Frozen, Detergents_Paper, Delicassen)...")
    spend_columns = ["Fresh", "Milk", "Grocery", "Frozen", "Detergents_Paper", "Delicassen"]
    hyp_results = {}
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
        assert "Channel" in tests_by_col
        assert "Region" in tests_by_col
        assert tests_by_col["Channel"]["test"] == "welch_t"
        assert tests_by_col["Channel"]["n_groups"] == 2
        assert tests_by_col["Region"]["test"] == "anova"
        assert tests_by_col["Region"]["n_groups"] == 3
        hyp_results[spend_col] = {
            "channel_p": tests_by_col["Channel"]["p_value"],
            "channel_lift_pct": tests_by_col["Channel"].get("lift_pct"),
            "region_p": tests_by_col["Region"]["p_value"],
        }

    # Measure 20 latency runs on /hypotheses
    print("  Measuring /hypotheses latency over 20 runs...")
    hyp_timings = []
    for _ in range(20):
        t0 = time.perf_counter()
        resp = client.post(
            "/api/v1/hypotheses",
            files={"file": ("Wholesale_customers_data.csv", raw)},
            data={"target": "Milk", "use_llm": "false"},
        )
        elapsed = (time.perf_counter() - t0) * 1000
        hyp_timings.append(elapsed)

    hyp_stats = calculate_latency_stats(hyp_timings)
    print(f"  Passed! /forecast non-error p50: {fc_stats['p50_ms']}ms | /hypotheses p50: {hyp_stats['p50_ms']}ms, p95: {hyp_stats['p95_ms']}ms")

    return {
        "status": "PASSED",
        "file": "Wholesale_customers_data.csv",
        "assertions": {
            "no_date_column_forecast_returns_clear_non_error": True,
            "channel_region_detected_as_categorical": True,
            "welch_t_test_on_channel_2_groups": True,
            "anova_on_region_3_groups": True,
            "validated_across_all_spend_columns": True,
        },
        "details": {
            "categorical_candidates": cats,
            "forecast_non_error_message": j_fc["message"],
            "spend_columns_tested": spend_columns,
            "spend_column_test_summaries": hyp_results,
        },
        "latency": {
            "forecast_no_date_api": fc_stats,
            "hypotheses_api": hyp_stats,
        },
    }


def main():
    print("=" * 70)
    print("Phase 3A Real-Dataset Validation & Latency Benchmarking (Agent 2)")
    print("=" * 70)

    # Locate dataset files
    day_path = find_dataset("day.csv")
    airline_path = find_dataset("airline-passengers.csv")
    retail_path = find_dataset("online_retail.csv")
    wholesale_path = find_dataset("Wholesale customers data.csv", "Wholesale_customers_data.csv")

    results: Dict[str, Any] = {
        "metadata": {
            "agent": "Agent 2 — Real-Dataset Validation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "python_version": sys.version,
            "platform": sys.platform,
            "budget_ms": 200,
        },
        "datasets": {},
        "summary": {
            "total_datasets": 4,
            "passed": 0,
            "failed": 0,
            "all_passed": False,
        },
    }

    try:
        results["datasets"]["day.csv"] = validate_day_csv(day_path)
        results["summary"]["passed"] += 1
    except Exception as e:
        print(f"FAILED on day.csv: {e}")
        results["datasets"]["day.csv"] = {"status": "FAILED", "error": str(e)}
        results["summary"]["failed"] += 1

    try:
        results["datasets"]["airline-passengers.csv"] = validate_airline_passengers(airline_path)
        results["summary"]["passed"] += 1
    except Exception as e:
        print(f"FAILED on airline-passengers.csv: {e}")
        results["datasets"]["airline-passengers.csv"] = {"status": "FAILED", "error": str(e)}
        results["summary"]["failed"] += 1

    try:
        results["datasets"]["online_retail.csv"] = validate_online_retail(retail_path)
        results["summary"]["passed"] += 1
    except Exception as e:
        print(f"FAILED on online_retail.csv: {e}")
        results["datasets"]["online_retail.csv"] = {"status": "FAILED", "error": str(e)}
        results["summary"]["failed"] += 1

    try:
        results["datasets"]["Wholesale_customers_data.csv"] = validate_wholesale_customers(wholesale_path)
        results["summary"]["passed"] += 1
    except Exception as e:
        print(f"FAILED on Wholesale_customers_data.csv: {e}")
        results["datasets"]["Wholesale_customers_data.csv"] = {"status": "FAILED", "error": str(e)}
        results["summary"]["failed"] += 1

    results["summary"]["all_passed"] = (results["summary"]["failed"] == 0)

    # Write report
    report_dir = BACKEND_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / "phase3a_validation.json"

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 70)
    print(f"Validation Complete! Results written to: {report_file}")
    print(f"Datasets Passed: {results['summary']['passed']}/{results['summary']['total_datasets']}")
    print(f"All Passed: {results['summary']['all_passed']}")
    print("=" * 70)

    if not results["summary"]["all_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
