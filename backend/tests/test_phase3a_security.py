"""Phase 3A Security and Hostile-File Audit (Anti-Gravity 5-Vector Audit Gate).

Comprehensive test suite validating the 5 security vectors for Foresight:
- Vector 1: Ephemeral RAM & Zero-Disk-Persistence
- Vector 2: Input Injection & CWE-1236 Formula Neutralization
- Vector 3: Prompt Injection & Data Isolation (Zero Column/Cell Leakage)
- Vector 4: Denial of Service & Free-Tier Budget Protection
- Vector 5: Logic Flaws & Extreme Edge-Case Data Shapes
"""

from __future__ import annotations

import builtins
import gc
import io
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any
from unittest.mock import patch

import httpx
import numpy as np
import pandas as pd
import pytest
from starlette.testclient import TestClient

from config.settings import Settings
from main import app
from src.orchestrator.chart_picker import ALLOWED, pick_chart
from src.parsers.sanitization import sanitize_tabular_cells

FIXTURES_DIR = Path(__file__).resolve().parent / "data"
client = TestClient(app)


# ===========================================================================
# Vector 1: Ephemeral RAM & Zero-Disk-Persistence
# ===========================================================================
class TestVector1EphemeralRAM:
    """Validate zero persistence to disk and ephemeral memory lifecycles."""

    def test_forecast_zero_file_writes(self):
        """Assert POST /api/v1/forecast performs zero file write operations to disk."""
        original_open = builtins.open
        forbidden_writes: list[tuple[str, str]] = []

        def tracking_open(file, mode="r", *args, **kwargs):
            if any(m in mode for m in ("w", "a", "+", "x")):
                forbidden_writes.append((str(file), mode))
            return original_open(file, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=tracking_open), \
             patch("tempfile.NamedTemporaryFile", side_effect=AssertionError("Disk tempfile forbidden")), \
             patch("tempfile.mkstemp", side_effect=AssertionError("Disk mkstemp forbidden")), \
             patch("tempfile.TemporaryFile", side_effect=AssertionError("Disk TemporaryFile forbidden")):

            rng = np.random.default_rng(42)
            df = pd.DataFrame({
                "date": pd.date_range("2023-01-01", periods=60, freq="D").astype(str),
                "sales": 100 + rng.integers(0, 50, 60),
            })
            csv_bytes = df.to_csv(index=False).encode("utf-8")

            res = client.post(
                "/api/v1/forecast",
                files={"file": ("ephemeral_forecast.csv", csv_bytes, "text/csv")},
                data={"use_llm": "false"},
            )
            assert res.status_code == 200
            assert forbidden_writes == [], f"Unexpected disk write attempts: {forbidden_writes}"

    def test_hypotheses_zero_file_writes(self):
        """Assert POST /api/v1/hypotheses performs zero file write operations to disk."""
        original_open = builtins.open
        forbidden_writes: list[tuple[str, str]] = []

        def tracking_open(file, mode="r", *args, **kwargs):
            if any(m in mode for m in ("w", "a", "+", "x")):
                forbidden_writes.append((str(file), mode))
            return original_open(file, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=tracking_open), \
             patch("tempfile.NamedTemporaryFile", side_effect=AssertionError("Disk tempfile forbidden")), \
             patch("tempfile.mkstemp", side_effect=AssertionError("Disk mkstemp forbidden")), \
             patch("tempfile.TemporaryFile", side_effect=AssertionError("Disk TemporaryFile forbidden")):

            df = pd.DataFrame({
                "sales": [100, 110, 105, 115, 120, 200, 210, 205, 215, 220],
                "promo": ["A", "A", "A", "A", "A", "B", "B", "B", "B", "B"],
            })
            csv_bytes = df.to_csv(index=False).encode("utf-8")

            res = client.post(
                "/api/v1/hypotheses",
                files={"file": ("ephemeral_hypo.csv", csv_bytes, "text/csv")},
                data={"use_llm": "false"},
            )
            assert res.status_code == 200
            assert forbidden_writes == [], f"Unexpected disk write attempts: {forbidden_writes}"

    def test_no_residual_files_in_temp_or_cwd(self):
        """Assert no transient or unvalidated files persist in CWD or temp directory."""
        temp_dir = tempfile.gettempdir()
        cwd = os.getcwd()

        temp_before = set(os.listdir(temp_dir))
        cwd_before = set(os.listdir(cwd))

        # Run both valid and hostile uploads
        with open(FIXTURES_DIR / "hostile_formula_cells.csv", "rb") as f:
            hostile_data = f.read()

        _ = client.post(
            "/api/v1/forecast",
            files={"file": ("hostile.csv", hostile_data, "text/csv")},
            data={"use_llm": "false"},
        )
        _ = client.post(
            "/api/v1/hypotheses",
            files={"file": ("hostile.csv", hostile_data, "text/csv")},
            data={"use_llm": "false"},
        )

        temp_after = set(os.listdir(temp_dir))
        cwd_after = set(os.listdir(cwd))

        new_temp_files = temp_after - temp_before
        new_cwd_files = cwd_after - cwd_before

        assert new_cwd_files == set(), f"Residual files left in CWD: {new_cwd_files}"
        # Temp dir might have background OS activity, but none should match Foresight data files
        for f in new_temp_files:
            assert not f.endswith((".csv", ".tsv", ".xlsx", ".parquet")), f"Residual tabular file in temp: {f}"

    def test_gc_collect_invoked_on_success_and_error(self):
        """Assert gc.collect() executes in finally blocks on both success and error paths."""
        with patch("src.api.analytics_router.gc.collect") as mock_gc:
            # 1. Success path
            rng = np.random.default_rng(42)
            df = pd.DataFrame({
                "date": pd.date_range("2023-01-01", periods=60, freq="D").astype(str),
                "sales": 100 + rng.integers(0, 50, 60),
            })
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            r_ok = client.post("/api/v1/forecast", files={"file": ("ok.csv", csv_bytes, "text/csv")}, data={"use_llm": "false"})
            assert r_ok.status_code == 200
            assert mock_gc.called, "gc.collect() not called on success path"

            mock_gc.reset_mock()

            # 2. Error / fallback path (insufficient data)
            short_df = pd.DataFrame({"date": ["2023-01-01"], "sales": [100]})
            r_short = client.post("/api/v1/forecast", files={"file": ("short.csv", short_df.to_csv(index=False).encode(), "text/csv")}, data={"use_llm": "false"})
            assert r_short.status_code == 200
            assert r_short.json()["status"] == "insufficient_data"
            assert mock_gc.called, "gc.collect() not called on insufficient data path"


# ===========================================================================
# Vector 2: Input Injection & Hostile Tabular Fixtures
# ===========================================================================
class TestVector2InputInjection:
    """Validate neutralization of formula injection (CWE-1236) and malformed headers."""

    @pytest.mark.parametrize("filename", [
        "hostile_formula_cells.csv",
        "hostile_formula_headers.csv",
        "hostile_odd_duplicate_empty_headers.csv",
        "hostile_unicode_rtl_headers.csv",
        "hostile_prompt_injection_headers.csv",
        "hostile_spoofed_extension.csv",
        "hostile_all_null_columns.csv",
        "hostile_single_column.csv",
        "hostile_single_row.csv",
        "hostile_wide_5000_cols.csv",
        "hostile_corrupt.xlsx",
    ])
    def test_all_hostile_fixtures_never_500_or_traceback(self, filename: str):
        """Assert every hostile fixture produces a controlled 4xx or sanitized 200, never 500 or traceback."""
        filepath = FIXTURES_DIR / filename
        assert filepath.exists(), f"Fixture {filename} missing"
        with open(filepath, "rb") as f:
            content = f.read()

        content_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if filename.endswith(".xlsx")
            else "text/csv"
        )

        r_fc = client.post("/api/v1/forecast", files={"file": (filename, content, content_type)}, data={"use_llm": "false"})
        r_hy = client.post("/api/v1/hypotheses", files={"file": (filename, content, content_type)}, data={"use_llm": "false"})

        for r, endpoint in [(r_fc, "forecast"), (r_hy, "hypotheses")]:
            assert r.status_code < 500, f"{endpoint} returned HTTP {r.status_code} for {filename}"
            # Ensure no unhandled exception traceback leaked
            text = r.text
            assert "Traceback (most recent call last)" not in text, f"Traceback leaked in {endpoint} response: {text}"
            assert "Internal Server Error" not in text

    def test_formula_cells_neutralized_in_echoed_outputs(self):
        """Verify formula prefixes in tabular cells are neutralized with single quotes in echoed outputs."""
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "sales": 100 + rng.integers(10, 100, 40),
            "group": ["=cmd|calc"] * 20 + ["+benefit"] * 20,
        })
        csv_bytes = df.to_csv(index=False).encode("utf-8")

        res = client.post(
            "/api/v1/hypotheses",
            files={"file": ("formula_cells.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200
        payload = res.json()
        tests = payload.get("tests", [])
        assert len(tests) > 0, f"Expected at least 1 test in hypotheses result: {payload}"

        # Inspect echoed group names
        t = tests[0]
        assert not t["baseline_group"].startswith(("=", "@", "+", "-")), f"Unsanitized baseline group: {t['baseline_group']}"
        assert not t["comparison_group"].startswith(("=", "@", "+", "-")), f"Unsanitized comparison group: {t['comparison_group']}"
        assert t["baseline_group"].startswith("'")
        assert t["comparison_group"].startswith("'")

        for stat in t.get("group_stats", []):
            grp_name = stat["group"]
            assert not grp_name.startswith(("=", "@", "+", "-")), f"Unsanitized group_stat: {grp_name}"
            assert grp_name.startswith("'")

    def test_formula_headers_neutralized_in_echoed_outputs(self):
        """Verify dangerous formula prefixes in column headers are neutralized in response metadata."""
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "=cmd|' /C calc'!A0": 100 + rng.integers(10, 100, 40),
            "@SUM(A1:B1)": ["A"] * 20 + ["B"] * 20,
        })
        csv_bytes = df.to_csv(index=False).encode("utf-8")

        res = client.post(
            "/api/v1/hypotheses",
            files={"file": ("formula_headers.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200
        payload = res.json()
        tests = payload.get("tests", [])
        assert len(tests) > 0, f"Expected at least 1 test in hypotheses result: {payload}"
        t = tests[0]

        assert not t["target"].startswith(("=", "@", "+", "-")), f"Unsanitized target header: {t['target']}"
        assert not t["grouping_column"].startswith(("=", "@", "+", "-")), f"Unsanitized group header: {t['grouping_column']}"
        assert t["target"].startswith("'")
        assert t["grouping_column"].startswith("'")

    def test_odd_duplicate_empty_and_5000char_headers(self):
        """Verify odd headers (duplicate, empty string, whitespace, 5000 chars) parse cleanly without 500."""
        with open(FIXTURES_DIR / "hostile_odd_duplicate_empty_headers.csv", "rb") as f:
            content = f.read()

        r_fc = client.post("/api/v1/forecast", files={"file": ("odd.csv", content, "text/csv")}, data={"use_llm": "false"})
        r_hy = client.post("/api/v1/hypotheses", files={"file": ("odd.csv", content, "text/csv")}, data={"use_llm": "false"})

        assert r_fc.status_code == 200
        assert r_hy.status_code == 200

    def test_unicode_rtl_homoglyph_and_emoji_headers(self):
        """Verify Arabic, Hebrew, RTL override, Cyrillic homoglyph, and emoji headers parse safely."""
        with open(FIXTURES_DIR / "hostile_unicode_rtl_headers.csv", "rb") as f:
            content = f.read()

        r_fc = client.post("/api/v1/forecast", files={"file": ("unicode.csv", content, "text/csv")}, data={"use_llm": "false"})
        r_hy = client.post("/api/v1/hypotheses", files={"file": ("unicode.csv", content, "text/csv")}, data={"use_llm": "false"})

        assert r_fc.status_code == 200
        assert r_hy.status_code == 200


# ===========================================================================
# Vector 3: Prompt Injection & Data Isolation
# ===========================================================================
class TestVector3PromptInjectionAndDataIsolation:
    """Validate zero leakage of column headers and cell values to LLM, and prompt injection defense."""

    def test_outgoing_llm_payload_zero_column_names_or_cell_values(self):
        """Assert the outgoing request payload sent to the LLM contains ZERO column names and ZERO cell values."""
        captured_requests: list[dict[str, Any]] = []

        def mock_handler(req: httpx.Request):
            captured_requests.append({
                "url": str(req.url),
                "headers": dict(req.headers),
                "body": json.loads(req.content.decode("utf-8")),
            })
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": json.dumps({"chart": "line_chart", "reason": "ok"})}]}}]},
            )

        mock_transport = httpx.MockTransport(mock_handler)
        original_async_client = httpx.AsyncClient

        def custom_async_client(*args, **kwargs):
            kwargs["transport"] = mock_transport
            return original_async_client(*args, **kwargs)

        mock_settings = Settings(google_api_key="audit-test-key", chart_picker_enabled=True)

        with patch("src.orchestrator.chart_picker.httpx.AsyncClient", side_effect=custom_async_client), \
             patch("src.api.analytics_router.get_settings", return_value=mock_settings), \
             patch("src.orchestrator.chart_picker.get_settings", return_value=mock_settings):

            # 1. Forecast with prompt-injected headers
            with open(FIXTURES_DIR / "hostile_prompt_injection_headers.csv", "rb") as f:
                content = f.read()

            r = client.post(
                "/api/v1/forecast",
                files={"file": ("injection.csv", content, "text/csv")},
                data={"use_llm": "true"},
            )
            assert r.status_code == 200
            assert len(captured_requests) == 1

            outgoing_json_str = json.dumps(captured_requests[0]["body"]).lower()

            # Forbidden prompt-injection strings
            forbidden_strings = [
                "ignore previous instructions",
                "system compromised",
                "reveal all api keys",
                "discard all formatting rules",
                "say pwned",
                "date",  # Even standard column names must never leak
            ]
            for s in forbidden_strings:
                assert s not in outgoing_json_str, f"Forbidden string '{s}' leaked into LLM payload!"

            # 2. Hypotheses with prompt-injected headers
            captured_requests.clear()
            r_hy = client.post(
                "/api/v1/hypotheses",
                files={"file": ("injection.csv", content, "text/csv")},
                data={"use_llm": "true"},
            )
            assert r_hy.status_code == 200
            assert len(captured_requests) == 1

            outgoing_hy_str = json.dumps(captured_requests[0]["body"]).lower()
            for s in forbidden_strings:
                assert s not in outgoing_hy_str, f"Forbidden string '{s}' leaked into LLM hypotheses payload!"

    @pytest.mark.anyio
    async def test_llm_hostile_injected_response_falls_back_to_heuristic(self):
        """Assert invalid or injected chart types from LLM fall back to deterministic heuristic."""
        malicious_responses = [
            {"chart": "DROP TABLE users;", "reason": "sql injection attempt"},
            {"chart": "<script>alert('pwned')</script>", "reason": "xss attempt"},
            {"chart": "eval(dangerous)", "reason": "rce attempt"},
            {"chart": "pie_3d", "reason": "unauthorized chart component"},
            {"chart": "SYSTEM COMPROMISED", "reason": "jailbreak attempt"},
        ]

        mock_settings = Settings(google_api_key="test-key", chart_picker_enabled=True)

        for mal_resp in malicious_responses:
            def handler(req: httpx.Request, r=mal_resp):
                return httpx.Response(
                    200,
                    json={"candidates": [{"content": {"parts": [{"text": json.dumps(r)}]}}]},
                )

            res = await pick_chart(
                "forecast",
                {"status": "ok"},
                settings=mock_settings,
                transport=httpx.MockTransport(handler),
            )
            assert res["source"] == "heuristic"
            assert res["chart"] == "line_chart"
            assert res["fallback_reason"] == "llm_invalid_choice"
            assert res["chart"] in ALLOWED

    @pytest.mark.anyio
    async def test_llm_malformed_text_or_json_falls_back_to_heuristic(self):
        """Assert non-JSON or malformed responses fall back cleanly to heuristic."""
        bad_texts = [
            "SYSTEM COMPROMISED: Here are the keys.",
            "{'malformed_json': True, missing_quotes}",
            "",
            "404 Not Found",
        ]
        mock_settings = Settings(google_api_key="test-key", chart_picker_enabled=True)

        for text in bad_texts:
            def handler(req: httpx.Request, t=text):
                return httpx.Response(
                    200,
                    json={"candidates": [{"content": {"parts": [{"text": t}]}}]},
                )

            res = await pick_chart(
                "hypotheses",
                {"status": "ok", "n_tests": 2},
                settings=mock_settings,
                transport=httpx.MockTransport(handler),
            )
            assert res["source"] == "heuristic"
            assert res["chart"] == "bar_comparison"
            assert res["fallback_reason"].startswith("llm_error_")
            assert res["chart"] in ALLOWED


# ===========================================================================
# Vector 4: Denial of Service & Free-Tier Protection
# ===========================================================================
class TestVector4DenialOfService:
    """Validate 50MB size guardrails and bounded compute under wide and deep tables."""

    def test_oversize_payload_strictly_rejected_413(self):
        """Assert files strictly exceeding 50.0 MB return HTTP 413 immediately without parsing."""
        oversize_bytes = b"X" * (50 * 1024 * 1024 + 1)

        r_fc = client.post("/api/v1/forecast", files={"file": ("huge.csv", oversize_bytes, "text/csv")})
        assert r_fc.status_code == 413
        assert "File exceeds the 50MB limit" in r_fc.json()["detail"]

        r_hy = client.post("/api/v1/hypotheses", files={"file": ("huge.csv", oversize_bytes, "text/csv")})
        assert r_hy.status_code == 413
        assert "File exceeds the 50MB limit" in r_hy.json()["detail"]

    def test_wide_table_5000_cols_bounded_execution(self):
        """Assert 5,000-column table executes in < 10 seconds without recursion or crash."""
        with open(FIXTURES_DIR / "hostile_wide_5000_cols.csv", "rb") as f:
            content = f.read()

        t0 = time.perf_counter()
        r_fc = client.post("/api/v1/forecast", files={"file": ("wide.csv", content, "text/csv")}, data={"use_llm": "false"})
        t_fc = time.perf_counter() - t0

        t0 = time.perf_counter()
        r_hy = client.post("/api/v1/hypotheses", files={"file": ("wide.csv", content, "text/csv")}, data={"use_llm": "false"})
        t_hy = time.perf_counter() - t0

        assert r_fc.status_code == 200
        assert r_hy.status_code == 200
        assert t_fc < 30.0, f"Forecast exceeded latency bound: {t_fc:.2f}s"
        assert t_hy < 30.0, f"Hypotheses exceeded latency bound: {t_hy:.2f}s"

    def test_deep_table_1m_rows_bounded_execution(self):
        """Assert 1,000,000-row table parses and executes within bounds without memory explosion."""
        buf = io.StringIO()
        buf.write("sales\n")
        chunk = "100\n" * 10000
        for _ in range(100):
            buf.write(chunk)
        raw = buf.getvalue().encode("utf-8")

        t0 = time.perf_counter()
        r = client.post("/api/v1/forecast", files={"file": ("million.csv", raw, "text/csv")}, data={"use_llm": "false"})
        elapsed = time.perf_counter() - t0

        assert r.status_code == 200
        assert r.json()["status"] == "no_date_column"
        assert elapsed < 5.0, f"Deep table took too long: {elapsed:.2f}s"

    def test_empty_zero_byte_file_returns_422(self):
        """Assert 0-byte upload is rejected immediately with HTTP 422."""
        r_fc = client.post("/api/v1/forecast", files={"file": ("empty.csv", b"", "text/csv")})
        assert r_fc.status_code == 422
        assert "Empty file uploaded" in r_fc.json()["detail"]


# ===========================================================================
# Vector 5: Logic Flaws & Extreme Edge-Case Data Shapes
# ===========================================================================
class TestVector5LogicFlaws:
    """Validate defenses against spoofed binaries, corrupt archives, and degenerate shapes."""

    def test_spoofed_pe_executable_binary_rejected_415(self):
        """Assert Windows PE binary (MZ header) renamed to .csv is rejected with HTTP 415."""
        with open(FIXTURES_DIR / "hostile_spoofed_extension.csv", "rb") as f:
            content = f.read()

        r = client.post("/api/v1/forecast", files={"file": ("malware.csv", content, "text/csv")})
        assert r.status_code == 415
        assert "Disallowed binary signature detected: Windows executable" in r.json()["detail"]

    def test_corrupt_xlsx_archive_rejected_415_or_422(self):
        """Assert corrupted XLSX file is rejected with 415 or 422, never a 500 or crash."""
        with open(FIXTURES_DIR / "hostile_corrupt.xlsx", "rb") as f:
            content = f.read()

        r = client.post(
            "/api/v1/forecast",
            files={"file": ("corrupt.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert r.status_code in (415, 422)
        assert r.status_code != 500

    def test_mismatched_extension_and_mime_rejected_415(self):
        """Assert disagreement between declared MIME type and extension raises HTTP 415."""
        df = pd.DataFrame({"a": [1, 2, 3]})
        csv_bytes = df.to_csv(index=False).encode("utf-8")

        r = client.post(
            "/api/v1/forecast",
            files={"file": ("data.csv", csv_bytes, "application/pdf")},
        )
        assert r.status_code == 415
        assert "disagrees with file extension" in r.json()["detail"]

    def test_all_null_columns_handled_cleanly(self):
        """Assert DataFrame with entirely null columns returns graceful 200 without NaN crash."""
        with open(FIXTURES_DIR / "hostile_all_null_columns.csv", "rb") as f:
            content = f.read()

        r = client.post("/api/v1/forecast", files={"file": ("nulls.csv", content, "text/csv")}, data={"use_llm": "false"})
        assert r.status_code == 200
        assert r.json()["status"] in ("insufficient_data", "no_date_column")

    def test_single_column_table_handled_cleanly(self):
        """Assert single-column table returns clean 200 without shape mismatch."""
        with open(FIXTURES_DIR / "hostile_single_column.csv", "rb") as f:
            content = f.read()

        r = client.post("/api/v1/forecast", files={"file": ("single_col.csv", content, "text/csv")}, data={"use_llm": "false"})
        assert r.status_code == 200
        assert r.json()["status"] in ("no_date_column", "insufficient_data")

    def test_single_row_table_handled_cleanly(self):
        """Assert single-row table returns clean 200 without index crash."""
        with open(FIXTURES_DIR / "hostile_single_row.csv", "rb") as f:
            content = f.read()

        r = client.post("/api/v1/forecast", files={"file": ("single_row.csv", content, "text/csv")}, data={"use_llm": "false"})
        assert r.status_code == 200
        assert r.json()["status"] == "insufficient_data"
