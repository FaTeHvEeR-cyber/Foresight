"""Empirical Adversarial Test Suite for Phase 3A (Challenger 2).

Challenges tabular ingestion, feature engineering, sanitization, and chart orchestration:
1. Ingestion robustness: empty files, corrupted files, files exceeding limit (>50MB), disallowed extensions (400, 413, 415, 422).
2. Formula injection: prefix neutralization (=, @, +, -) in tabular cells, preservation of genuine numerics, endpoint behavior.
3. Chart picker resilience: mock LLM errors (500, malformed JSON, empty response), 429 throttling, timeouts, invalid chart types, and deterministic fallback.
"""

import io
import json
import httpx
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from config.settings import Settings
from main import app
from src.analytics import feature_pipeline as fp
from src.analytics.forecast_engine import run_forecast
from src.analytics.hypothesis_engine import run_hypotheses
from src.analytics.loader import UnsupportedFormat, load_tabular
from src.orchestrator.chart_picker import ALLOWED, heuristic_pick, pick_chart
from src.parsers.sanitization import (
    FileSizeError,
    MimeTypeError,
    sanitize_tabular_cells,
    validate_file_size,
    validate_mime_and_extension,
)
from tests.conftest import to_csv_bytes

client = TestClient(app)


# ==============================================================================
# 1. INGESTION & BOUNDARY STRESS TESTS
# ==============================================================================


class TestIngestionBoundaries:
    """Challenge ingestion against empty files, corrupt bytes, oversize payloads, and bad extensions."""

    def test_empty_files_raise_422_or_400(self):
        """0-byte file uploads should be cleanly rejected with 422 or 400, never 500."""
        # /api/v1/forecast with empty CSV
        r_fc = client.post("/api/v1/forecast", files={"file": ("empty.csv", b"")}, data={"use_llm": "false"})
        assert r_fc.status_code == 422, f"Expected 422 for empty CSV in forecast, got {r_fc.status_code}: {r_fc.text}"
        assert "EmptyDataError" in r_fc.json().get("detail", "") or "empty" in r_fc.json().get("detail", "").lower()

        # /api/v1/hypotheses with empty CSV
        r_hyp = client.post("/api/v1/hypotheses", files={"file": ("empty.csv", b"")}, data={"use_llm": "false"})
        assert r_hyp.status_code == 422, f"Expected 422 for empty CSV in hypotheses, got {r_hyp.status_code}: {r_hyp.text}"

        # /upload endpoint (Phase 2) with empty file rejects with 400
        r_up = client.post("/upload", files={"file": ("empty.csv", b"", "text/csv")})
        assert r_up.status_code == 400, f"Expected 400 for empty file on /upload, got {r_up.status_code}: {r_up.text}"
        assert "empty" in r_up.json().get("detail", "").lower()

    def test_corrupted_files_return_422_not_500(self):
        """Corrupted tabular payloads (binary junk, invalid zip, broken parquet) must return 422, not crash."""
        # Corrupted CSV (null bytes and malformed records)
        corrupted_csv = b"\x00\xff\xfe\x00malformed,csv,header\n\x00\x00invalid\xff\xfe"
        r_csv = client.post("/api/v1/forecast", files={"file": ("broken.csv", corrupted_csv)}, data={"use_llm": "false"})
        assert r_csv.status_code in (422, 415), f"Expected 422/415 for corrupted CSV, got {r_csv.status_code}: {r_csv.text}"

        # Corrupted XLSX (random bytes with .xlsx extension)
        corrupted_xlsx = b"PK\x03\x04\x00\x00NOT_A_VALID_EXCEL_ZIP_ARCHIVE"
        r_xlsx = client.post("/api/v1/forecast", files={"file": ("broken.xlsx", corrupted_xlsx)}, data={"use_llm": "false"})
        assert r_xlsx.status_code == 422, f"Expected 422 for corrupted XLSX, got {r_xlsx.status_code}: {r_xlsx.text}"

        # Corrupted Parquet (truncated or broken parquet magic)
        corrupted_parquet = b"PAR1invalid_bytes_truncated"
        r_parquet = client.post("/api/v1/forecast", files={"file": ("broken.parquet", corrupted_parquet)}, data={"use_llm": "false"})
        assert r_parquet.status_code == 422, f"Expected 422 for corrupted Parquet, got {r_parquet.status_code}: {r_parquet.text}"

        # Same checks on /api/v1/hypotheses
        r_hyp_xlsx = client.post("/api/v1/hypotheses", files={"file": ("broken.xlsx", corrupted_xlsx)}, data={"use_llm": "false"})
        assert r_hyp_xlsx.status_code == 422, f"Expected 422 for corrupted XLSX, got {r_hyp_xlsx.status_code}"

    def test_disallowed_extensions_return_415(self):
        """Files with non-tabular extensions must be rejected with 415 Unsupported Media Type."""
        disallowed = [
            ("script.py", b"print('hello')"),
            ("payload.exe", b"\x4d\x5a\x90\x00"),
            ("archive.zip", b"PK\x03\x04"),
            ("shell.sh", b"#!/bin/bash\nrm -rf /"),
            ("document.pdf", b"%PDF-1.4 dummy pdf"),
            ("notes.docx", b"PK\x03\x04 dummy docx"),
            ("config.json", b'{"key": "value"}'),
            ("no_extension", b"1,2,3\n4,5,6"),
        ]
        for fname, content in disallowed:
            r = client.post("/api/v1/forecast", files={"file": (fname, content)}, data={"use_llm": "false"})
            assert r.status_code == 415, f"Expected 415 for {fname}, got {r.status_code}: {r.text}"
            assert "Unsupported" in r.json().get("detail", "")

            r_h = client.post("/api/v1/hypotheses", files={"file": (fname, content)}, data={"use_llm": "false"})
            assert r_h.status_code == 415, f"Expected 415 for {fname} in hypotheses, got {r_h.status_code}: {r_h.text}"

    def test_payload_exceeding_limit_returns_413(self, monkeypatch):
        """Uploads exceeding max_upload_bytes must trigger HTTP 413 Payload Too Large."""
        import src.api.analytics_router as ar
        # Set artificially low limit for fast unit test
        monkeypatch.setattr(ar, "get_settings", lambda: Settings(max_upload_bytes=1024))

        # Payload of 2KB > 1KB limit
        oversized = b"a" * 2048
        r = client.post("/api/v1/forecast", files={"file": ("big.csv", oversized)}, data={"use_llm": "false"})
        assert r.status_code == 413, f"Expected 413 for oversized file, got {r.status_code}: {r.text}"
        assert "exceeds" in r.json().get("detail", "").lower()

        r_hyp = client.post("/api/v1/hypotheses", files={"file": ("big.csv", oversized)}, data={"use_llm": "false"})
        assert r_hyp.status_code == 413, f"Expected 413 for oversized file in hypotheses, got {r_hyp.status_code}: {r_hyp.text}"

    def test_direct_loader_unsupported_formats(self):
        """Direct invocation of load_tabular with invalid extensions raises UnsupportedFormat."""
        with pytest.raises(UnsupportedFormat):
            load_tabular(b"test", "test.exe")
        with pytest.raises(UnsupportedFormat):
            load_tabular(b"test", "test.pdf")
        with pytest.raises(UnsupportedFormat):
            load_tabular(b"test", "")


# ==============================================================================
# 2. FORMULA INJECTION & SANITIZATION CHALLENGE
# ==============================================================================


class TestFormulaInjection:
    """Stress-test formula injection prefixes (=, @, +, -) in tabular cells per spec §4.2."""

    def test_sanitization_neutralizes_dangerous_prefixes(self):
        """sanitize_tabular_cells prepends single quote or strips formula prefix characters."""
        df = pd.DataFrame({
            "code": ["=SUM(A1:A10)", "@cmd", "+12345", "-dangerous"],
            "hyperlink": ["=HYPERLINK(\"http://malicious.site\", \"Click Me\")", "normal", "+calc", "-cmd"],
            "num_float": [-42.5, 10.0, -0.01, 99.9],
            "num_int": [-100, 200, -300, 400],
            "boolean_col": [True, False, True, False],
        })

        # Test quote method (default)
        sanitized_quote = sanitize_tabular_cells(df, method="quote")
        for val in sanitized_quote["code"]:
            assert val.startswith("'"), f"Expected quoted prefix for {val}"
        assert sanitized_quote["code"][0] == "'=SUM(A1:A10)"
        assert sanitized_quote["code"][1] == "'@cmd"
        assert sanitized_quote["code"][2] == "'+12345"
        assert sanitized_quote["code"][3] == "'-dangerous"

        # Genuine numeric columns MUST remain uncorrupted
        assert (sanitized_quote["num_float"] == df["num_float"]).all()
        assert (sanitized_quote["num_int"] == df["num_int"]).all()
        assert (sanitized_quote["boolean_col"] == df["boolean_col"]).all()

        # Test strip method
        sanitized_strip = sanitize_tabular_cells(df, method="strip")
        assert sanitized_strip["code"][0] == "SUM(A1:A10)"
        assert sanitized_strip["code"][1] == "cmd"
        assert sanitized_strip["code"][2] == "12345"
        assert sanitized_strip["code"][3] == "dangerous"

    def test_formula_injection_in_categorical_columns(self):
        """Categorical series with formula prefixes should be safely sanitized."""
        df = pd.DataFrame({
            "cat": pd.Categorical(["=EXEC", "@DDE", "+ADMIN", "-ROOT"]),
            "val": [1.0, 2.0, 3.0, 4.0],
        })
        sanitized = sanitize_tabular_cells(df, method="quote")
        assert list(sanitized["cat"]) == ["'=EXEC", "'@DDE", "'+ADMIN", "'-ROOT"]

    def test_forecast_pipeline_under_formula_injected_data(self):
        """Feature pipeline and forecast endpoint under formula injection prefixes."""
        # Create valid time series with formula prefixes injected into text / categorical columns
        dates = pd.date_range("2020-01-01", periods=100, freq="D")
        df = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "target": np.random.default_rng(42).normal(100, 10, 100),
            "promo_name": ["=PROMO_A" if i % 2 == 0 else "@PROMO_B" for i in range(100)],
        })
        csv_bytes = to_csv_bytes(df)
        r = client.post(
            "/api/v1/forecast",
            files={"file": ("injected.csv", csv_bytes)},
            data={"target": "target", "date_col": "date", "use_llm": "false"},
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        res = r.json()
        assert res["status"] == "ok"
        assert len(res["forecast"]["values"]) > 0

    def test_hypotheses_pipeline_under_formula_injected_group_names(self):
        """Hypotheses engine with formula prefixes in category groupings."""
        n = 100
        df = pd.DataFrame({
            "group": ["=GROUP_A" if i < 50 else "@GROUP_B" for i in range(n)],
            "metric": np.random.default_rng(0).normal(50, 5, n),
        })
        csv_bytes = to_csv_bytes(df)
        r = client.post(
            "/api/v1/hypotheses",
            files={"file": ("hypo_injected.csv", csv_bytes)},
            data={"target": "metric", "group_cols": "group", "use_llm": "false"},
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        res = r.json()
        assert res["status"] == "ok"
        assert len(res["tests"]) == 1


# ==============================================================================
# 3. CHART PICKER ADVERSARIAL & HEURISTIC FALLBACK CHALLENGE
# ==============================================================================


class TestChartPickerAdversarial:
    """Stress-test chart picker under simulated upstream failures, 429 throttling, and malformed outputs."""

    def _settings(self, key="valid-mock-key"):
        return Settings(google_api_key=key, llm_model="gemini-3.8-flash", chart_picker_enabled=True)

    @pytest.mark.anyio
    async def test_llm_http_500_error_falls_back_to_heuristic(self):
        """Upstream 500 Internal Server Error must fall back to deterministic heuristic."""
        def handler(req: httpx.Request):
            return httpx.Response(500, json={"error": {"code": 500, "message": "Internal error"}})

        transport = httpx.MockTransport(handler)
        res = await pick_chart("forecast", {"status": "ok"}, settings=self._settings(), transport=transport)
        assert res["source"] == "heuristic"
        assert res["chart"] == "line_chart"
        assert res["fallback_reason"] == "llm_http_500"
        assert res["chart"] in ALLOWED

    @pytest.mark.anyio
    async def test_llm_http_429_throttling_falls_back_to_heuristic(self):
        """HTTP 429 Rate Limit / Quota Exhaustion must fall back cleanly with fallback_reason='llm_http_429'."""
        def handler(req: httpx.Request):
            return httpx.Response(429, json={"error": {"code": 429, "message": "Resource exhausted"}})

        transport = httpx.MockTransport(handler)
        res = await pick_chart("hypotheses", {"status": "ok", "n_tests": 3}, settings=self._settings(), transport=transport)
        assert res["source"] == "heuristic"
        assert res["chart"] == "bar_comparison"
        assert res["fallback_reason"] == "llm_http_429"
        assert res["chart"] in ALLOWED

    @pytest.mark.anyio
    async def test_llm_network_timeout_falls_back_to_heuristic(self):
        """Network timeout during LLM call must fall back cleanly to heuristic without hanging."""
        def handler(req: httpx.Request):
            raise httpx.ReadTimeout("Request timed out after 3.0s")

        transport = httpx.MockTransport(handler)
        res = await pick_chart("segmentation", {"status": "ok"}, settings=self._settings(), transport=transport)
        assert res["source"] == "heuristic"
        assert res["chart"] == "scatter_cluster"
        assert "Timeout" in res["fallback_reason"] or "ReadTimeout" in res["fallback_reason"]

    @pytest.mark.anyio
    async def test_llm_returns_invalid_or_hallucinated_chart_type(self):
        """If LLM hallucinates an unapproved chart (e.g. pie_chart, 3d_scatter), fall back to heuristic."""
        hallucinations = ["pie_chart", "3d_scatter", "bubble_chart", "heatmap", "radar", "exploit_widget", ""]
        for hallucinated in hallucinations:
            def handler(req: httpx.Request):
                body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"chart": hallucinated, "reason": "creative chart"})}]}}]}
                return httpx.Response(200, json=body)

            transport = httpx.MockTransport(handler)
            res = await pick_chart("forecast", {"status": "ok"}, settings=self._settings(), transport=transport)
            assert res["source"] == "heuristic", f"Failed to reject hallucinated chart: {hallucinated}"
            assert res["chart"] == "line_chart"
            assert res["fallback_reason"] == "llm_invalid_choice"
            assert res["chart"] in ALLOWED

    @pytest.mark.anyio
    async def test_llm_returns_malformed_json_or_missing_keys(self):
        """Malformed JSON or missing candidates structure must be handled gracefully."""
        bad_payloads = [
            b"Internal Gateway Error (non-json text)",
            b"{}",
            b'{"candidates": []}',
            b'{"candidates": [{"content": {}}]}',
            b'{"candidates": [{"content": {"parts": [{"text": "NOT A JSON STRING"}]}}]}',
            b'{"candidates": [{"content": {"parts": [{"text": "{\"unrelated\": 123}"}]}}]}',
        ]
        for payload in bad_payloads:
            def handler(req: httpx.Request):
                return httpx.Response(200, content=payload, headers={"Content-Type": "application/json"})

            transport = httpx.MockTransport(handler)
            res = await pick_chart("forecast", {"status": "ok"}, settings=self._settings(), transport=transport)
            assert res["source"] == "heuristic"
            assert res["chart"] == "line_chart"
            assert "llm_" in res.get("fallback_reason", "")

    def test_heuristic_pick_coverage_all_scenarios(self):
        """Verify heuristic_pick behavior across all result kinds and edge conditions."""
        # Forecast ok -> line_chart
        assert heuristic_pick("forecast", {"status": "ok"})[0] == "line_chart"
        # Forecast insufficient_data -> kpi_card
        assert heuristic_pick("forecast", {"status": "insufficient_data"})[0] == "kpi_card"
        assert heuristic_pick("forecast", {"status": "error"})[0] == "kpi_card"

        # Hypotheses with tests -> bar_comparison
        assert heuristic_pick("hypotheses", {"status": "ok", "n_tests": 2})[0] == "bar_comparison"
        # Hypotheses with 0 tests -> kpi_card
        assert heuristic_pick("hypotheses", {"status": "ok", "n_tests": 0})[0] == "kpi_card"

        # Segmentation ok -> scatter_cluster
        assert heuristic_pick("segmentation", {"status": "ok"})[0] == "scatter_cluster"
        # Segmentation not ok -> kpi_card
        assert heuristic_pick("segmentation", {"status": "error"})[0] == "kpi_card"

        # Unknown kind -> kpi_card
        assert heuristic_pick("unknown_kind", {})[0] == "kpi_card"


# ==============================================================================
# 4. FEATURE PIPELINE & HYPOTHESIS EDGE CASE TESTING
# ==============================================================================


class TestPipelineEdgeCases:
    """Stress-test feature pipeline under extreme dates, single-category inputs, and boundary data."""

    def test_extreme_and_leap_dates(self):
        """Pipeline handles leap year dates (Feb 29) and short series raises SeriesTooShort on forecast."""
        leap_dates = pd.date_range("2024-02-25", "2024-03-05", freq="D")
        df_leap = pd.DataFrame({
            "Date": leap_dates.strftime("%Y-%m-%d"),
            "Sales": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0],
        })
        prep = fp.prepare_series(df_leap, target="Sales", date_col="Date")
        assert prep.cfg.label == "D"
        # Length 10 is too short for full lag set -> should raise SeriesTooShort cleanly on forecast
        with pytest.raises(fp.SeriesTooShort) as exc_info:
            run_forecast(prep)
        assert "Upload a longer history" in str(exc_info.value)

    def test_non_monotonic_dates_reindexed(self):
        """Dates uploaded in reverse order or shuffled are handled and reindexed correctly."""
        d = pd.date_range("2021-01-01", periods=100, freq="D")
        shuffled = d.to_series().sample(frac=1.0, random_state=42).values
        df = pd.DataFrame({
            "Date": pd.to_datetime(shuffled).strftime("%Y-%m-%d"),
            "Target": np.arange(100, dtype=float),
        })
        prep = fp.prepare_series(df, target="Target", date_col="Date")
        assert prep.y.index.is_monotonic_increasing

    def test_single_category_hypotheses_handled(self):
        """If a grouping column has only 1 unique category, Welch's t-test should return insufficient_data without crashing."""
        df = pd.DataFrame({
            "SingleCategory": ["GroupA"] * 50,
            "Target": np.random.default_rng(0).normal(10, 1, 50),
        })
        csv_bytes = to_csv_bytes(df)
        r = client.post(
            "/api/v1/hypotheses",
            files={"file": ("single_cat.csv", csv_bytes)},
            data={"target": "Target", "group_cols": "SingleCategory", "use_llm": "false"},
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        res = r.json()
        assert res["status"] == "insufficient_data"
        assert "No usable grouping columns" in res["message"]
        # No 2-group comparison possible, so tests list should be empty and chart should fall back to kpi_card
        assert len(res["tests"]) == 0
        assert res["recommended_visualization"]["chart"] == "kpi_card"

    def test_constant_target_series(self):
        """Constant target (zero variance) should not crash forecasting."""
        d = pd.date_range("2020-01-01", periods=100, freq="D")
        df = pd.DataFrame({
            "Date": d.strftime("%Y-%m-%d"),
            "Value": [50.0] * 100,
        })
        prep = fp.prepare_series(df, target="Value", date_col="Date")
        res = run_forecast(prep, horizon=7)
        assert res["status"] == "ok"
        assert len(res["forecast"]["values"]) == 7
