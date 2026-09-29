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

        # Segmentation degraded/error
        seg_tokens, _ = heuristic_pick("segmentation", {"status": "insufficient_data"})
        assert seg_tokens == ["kpi_card"]

    def test_segmentation_payload_contract(self):
        """Verify that POST /api/v1/segmentation returns all required fields for every token in heuristic_pick:
        scatter_cluster, outlier_table, heatmap_correlation.
        """
        rng = np.random.default_rng(42)
        n = 80
        df = pd.DataFrame({
            "feature_1": rng.normal(10, 2, n),
            "feature_2": rng.normal(20, 5, n),
            "feature_3": rng.exponential(1.5, n),
            "feature_4": rng.uniform(0, 100, n),
        })
        csv_bytes = _to_csv(df)

        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("segmentation.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200, f"Segmentation request failed: {res.text}"
        payload = res.json()
        assert payload["status"] == "ok"

        # Check heuristic pick for segmentation
        tokens, reason = heuristic_pick("segmentation", {"status": "ok"})
        assert tokens == ["scatter_cluster", "outlier_table", "heatmap_correlation"]
        assert payload["recommended_visualization"]["charts"] == tokens
        assert payload["recommended_visualization"]["chart"] == "scatter_cluster"

        # 1. scatter_cluster required fields: pca_x, pca_y, cluster_assignments, optimal_k, clustering_method
        assert "pca_x" in payload and "pca_y" in payload
        assert "cluster_assignments" in payload
        assert len(payload["pca_x"]) == len(payload["pca_y"]) == len(payload["cluster_assignments"])
        assert len(payload["pca_x"]) == n
        assert all(isinstance(v, (int, float)) for v in payload["pca_x"])
        assert all(isinstance(v, (int, float)) for v in payload["pca_y"])
        assert all(isinstance(c, int) for c in payload["cluster_assignments"])
        assert payload["optimal_k"] in (2, 3, 4, 5, 6)
        assert payload["clustering_method"] in ("data_driven_silhouette", "fallback_default")

        # Frontend ScatterCluster component compatibility checks
        assert "points" in payload and len(payload["points"]) == n
        assert all("x" in pt and "y" in pt and "clusterId" in pt for pt in payload["points"])
        assert "outlier_mask" in payload and len(payload["outlier_mask"]) == n

        # 2. outlier_table required fields: outlier_records with id, anomaly_score, and original fields
        assert "outlier_records" in payload
        outliers = payload["outlier_records"]
        assert isinstance(outliers, list)
        assert len(outliers) > 0
        assert len(outliers) <= 100

        # Monotonic descending anomaly scores
        scores = [row["anomaly_score"] for row in outliers]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Outlier scores not sorted descending at index {i}: {scores}"

        for row in outliers:
            assert "id" in row, f"Outlier record missing 'id': {row}"
            assert "anomaly_score" in row, f"Outlier record missing 'anomaly_score': {row}"
            assert isinstance(row["anomaly_score"], (int, float))
            # Must carry original features for OutlierTable rendering
            assert "feature_1" in row
            assert "feature_2" in row

        # 3. heatmap_correlation required fields: correlation_matrix (+ correlation_matrix_truncated flag)
        assert "correlation_matrix" in payload
        corr = payload["correlation_matrix"]
        assert "columns" in corr and len(corr["columns"]) == 4
        assert "values" in corr and len(corr["values"]) == 4
        assert "points" in corr and len(corr["points"]) == 16
        for pt in corr["points"]:
            assert "x" in pt and "y" in pt and "value" in pt
            assert -1.0 <= pt["value"] <= 1.0
        assert "correlation_matrix_truncated" in payload
        assert payload["correlation_matrix_truncated"] is False

        # 4. Row-cap and subsampling metadata flags
        assert "subsampled" in payload
        assert payload["subsampled"] is False
        assert "original_row_count" in payload
        assert payload["original_row_count"] == n

