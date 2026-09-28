"""Payload contract tests verifying that every token in heuristic_pick has its required fields in the response.

Endpoints tested:
  - POST /api/v1/forecast -> ["line_chart", "forecast_band_chart", "kpi_card"]
  - POST /api/v1/hypotheses -> ["bar_comparison", "box_plot"]
"""
import io
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from src.analytics.hypothesis_engine import run_hypotheses
from src.orchestrator.chart_picker import heuristic_pick
from src.orchestrator.chart_registry import ALLOWED

client = TestClient(app)


def _to_csv(df: pd.DataFrame) -> bytes:
    b = io.BytesIO()
    df.to_csv(b, index=False)
    return b.getvalue()


@pytest.fixture
def forecast_df() -> pd.DataFrame:
    """Synthetic time-series dataset with 60 daily observations."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2023-01-01", periods=60, freq="D")
    trend = np.linspace(50, 150, 60)
    noise = rng.normal(0, 5, 60)
    return pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "sales": trend + noise})


@pytest.fixture
def hypothesis_df() -> pd.DataFrame:
    """Dataset with categorical grouping columns and numeric target."""
    rng = np.random.default_rng(42)
    n = 60
    return pd.DataFrame({
        "group_2": ["A"] * 30 + ["B"] * 30,
        "group_3": ["X"] * 20 + ["Y"] * 20 + ["Z"] * 20,
        "metric": rng.normal(100, 15, n),
    })


class TestPayloadContract:
    def test_forecast_payload_contract(self, forecast_df):
        """Verify that POST /api/v1/forecast returns all required fields for every token in heuristic_pick."""
        csv_bytes = _to_csv(forecast_df)
        res = client.post(
            "/api/v1/forecast",
            files={"file": ("forecast.csv", csv_bytes, "text/csv")},
            data={"target": "sales", "date_col": "date", "horizon": 7, "use_llm": "false"},
        )
        assert res.status_code == 200, f"Forecast failed: {res.text}"
        payload = res.json()
        assert payload["status"] == "ok"

        # Check heuristic pick for forecast
        tokens, reason = heuristic_pick("forecast", {"status": "ok"})
        assert tokens == ["line_chart", "forecast_band_chart", "kpi_card"]
        assert payload["recommended_visualization"]["charts"] == tokens

        # 1. line_chart required fields: series.dates, series.actuals, forecast.dates, forecast.values
        series = payload.get("series", {})
        forecast_block = payload.get("forecast", {})
        assert "dates" in series and len(series["dates"]) > 0
        assert "actuals" in series and len(series["actuals"]) > 0
        assert len(series["dates"]) == len(series["actuals"])
        assert "dates" in forecast_block and len(forecast_block["dates"]) == 7
        assert "values" in forecast_block and len(forecast_block["values"]) == 7
        assert all(isinstance(v, (int, float)) for v in forecast_block["values"])

        # 2. forecast_band_chart required fields: lower, upper CI arrays alongside line_chart fields
        assert "lower" in forecast_block and len(forecast_block["lower"]) == 7
        assert "upper" in forecast_block and len(forecast_block["upper"]) == 7
        for lo, val, hi in zip(forecast_block["lower"], forecast_block["values"], forecast_block["upper"]):
            assert lo <= val <= hi, f"CI violation: lower={lo} <= value={val} <= upper={hi}"

        # 3. kpi_card required fields: status, target, and headline metrics
        assert payload.get("status") == "ok"
        assert payload.get("dataset", {}).get("target") == "sales"
        metrics = payload.get("metrics", {})
        selected_model = payload.get("selected_model")
        assert selected_model in metrics
        assert "rmse" in metrics[selected_model]
        assert "mae" in metrics[selected_model]

    def test_hypotheses_payload_contract(self, hypothesis_df):
        """Verify that POST /api/v1/hypotheses returns all required fields for every token in heuristic_pick."""
        csv_bytes = _to_csv(hypothesis_df)
        res = client.post(
            "/api/v1/hypotheses",
            files={"file": ("hypo.csv", csv_bytes, "text/csv")},
            data={"target": "metric", "group_cols": "group_2,group_3", "use_llm": "false"},
        )
        assert res.status_code == 200, f"Hypotheses failed: {res.text}"
        payload = res.json()
        assert payload["status"] == "ok"
        tests = payload.get("tests", [])
        assert len(tests) >= 2

        # Check heuristic pick for hypotheses
        tokens, reason = heuristic_pick("hypotheses", {"status": "ok", "n_tests": len(tests)})
        assert tokens == ["bar_comparison", "box_plot"]
        assert payload["recommended_visualization"]["charts"] == tokens

        for t in tests:
            gstats = t.get("group_stats", [])
            assert len(gstats) >= 2
            assert len(gstats) <= 12, "group_stats must be capped at 12"

            # 1. bar_comparison required fields: group, mean, std
            for stat in gstats:
                assert "group" in stat and stat["group"] is not None
                assert "n" in stat and stat["n"] >= 5
                assert "mean" in stat and isinstance(stat["mean"], (int, float))
                assert "std" in stat and isinstance(stat["std"], (int, float))

            # 2. box_plot required fields: min, q1, median, q3, max
            for stat in gstats:
                for k in ("min", "q1", "median", "q3", "max"):
                    assert k in stat, f"Missing {k} in group_stats: {stat}"
                    assert isinstance(stat[k], (int, float))
                # Statistical monotonic inequality: min <= q1 <= median <= q3 <= max
                assert stat["min"] <= stat["q1"] <= stat["median"] <= stat["q3"] <= stat["max"], (
                    f"Percentile monotonicity violated in {stat}"
                )

    def test_hypotheses_caps_groups_at_12(self):
        """Verify that run_hypotheses strictly caps returned groups at 12 (top by n)."""
        rng = np.random.default_rng(42)
        # Create 20 groups with descending frequencies (200, 190, 180, ... 10 rows)
        rows = []
        for i in range(20):
            grp_name = f"grp_{i:02d}"
            n_rows = 10 + i * 10
            vals = rng.normal(50, 10, n_rows)
            for v in vals:
                rows.append({"category": grp_name, "value": v})
        df = pd.DataFrame(rows)

        res = run_hypotheses(df, target="value", group_cols=["category"])
        assert res["status"] == "ok"
        test_res = res["tests"][0]

        assert test_res["n_groups"] == 12, f"Expected 12 groups, got {test_res['n_groups']}"
        assert len(test_res["group_stats"]) == 12

        # The 12 kept groups must be the ones with the largest sample sizes
        # In our generator, grp_08 to grp_19 have the largest n_rows (>= 90 rows)
        kept_groups = {s["group"] for s in test_res["group_stats"]}
        expected_top_12 = {f"grp_{i:02d}" for i in range(8, 20)}
        assert kept_groups == expected_top_12, f"Expected top 12 groups {expected_top_12}, got {kept_groups}"

    def test_degraded_states_payload_contract(self):
        """Verify fallback to kpi_card on insufficient data and presence of message."""
        # Forecast insufficient data
        fc_tokens, _ = heuristic_pick("forecast", {"status": "insufficient_data"})
        assert fc_tokens == ["kpi_card"]

        # Hypotheses zero tests
        hyp_tokens, _ = heuristic_pick("hypotheses", {"status": "insufficient_data", "n_tests": 0})
        assert hyp_tokens == ["kpi_card"]
