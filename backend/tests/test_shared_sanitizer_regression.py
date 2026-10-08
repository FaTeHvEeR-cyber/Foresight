"""Shared Sanitizer and Error-Handling Regression Suite (WS-A).

Comprehensive regression tests for:
- POST /api/v1/upload
- POST /api/v1/forecast
- POST /api/v1/hypotheses

Verifies:
1. Column header sanitization collisions (=a, '=a, ''=a) and unique deduplication
2. Leading whitespace and full-width formula injection neutralization
3. Dangerous prefix only and empty headers
4. Filename security (path traversal, null bytes, long names, backslash paths) with zero path leakage
5. Finding 3 equivalent: unexpected non-ValueError exceptions produce controlled 500 without stack trace
   and ensure del df; gc.collect() executes in finally.
6. Deep recursive string inspection across response keys and values.
"""
from __future__ import annotations

import gc
import io
import os
from unittest.mock import patch
from typing import Any, List

import numpy as np
import pandas as pd
import pytest
from starlette.testclient import TestClient

from main import app

client = TestClient(app)


def inspect_strings_for_raw_formulas(obj: Any, path: str = "root") -> List[str]:
    """Recursively search any JSON-like data structure for raw unescaped formula strings."""
    violations: List[str] = []
    if isinstance(obj, str):
        stripped = obj.lstrip()
        if stripped and stripped[0] in ("=", "@", "+", "-", "\uff1d", "\uff20", "\uff0b", "\uff0d"):
            if not obj.startswith("'"):
                violations.append(f"{path}: {obj!r}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                stripped_k = k.lstrip()
                if stripped_k and stripped_k[0] in ("=", "@", "+", "-", "\uff1d", "\uff20", "\uff0b", "\uff0d"):
                    if not k.startswith("'"):
                        violations.append(f"{path}.<key:{k}>")
            violations.extend(inspect_strings_for_raw_formulas(v, f"{path}.{k}"))
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            violations.extend(inspect_strings_for_raw_formulas(item, f"{path}[{i}]"))
    return violations


def _make_forecast_csv(headers: list[str], n_rows: int = 40) -> bytes:
    dates = pd.date_range("2020-01-01", periods=n_rows, freq="D").strftime("%Y-%m-%d")
    data = {"date": dates}
    for h in headers:
        data[h] = [float(10.0 + i) for i in range(n_rows)]
    df = pd.DataFrame(data)
    return df.to_csv(index=False).encode("utf-8")


def _make_hypo_csv(headers: list[str], n_rows: int = 40) -> bytes:
    groups = ["A" if i % 2 == 0 else "B" for i in range(n_rows)]
    data = {"grp": groups}
    for h in headers:
        data[h] = [float(10.0 + i) for i in range(n_rows)]
    df = pd.DataFrame(data)
    return df.to_csv(index=False).encode("utf-8")


def _make_upload_csv(headers: list[str], n_rows: int = 10) -> bytes:
    data = {}
    for h in headers:
        data[h] = [float(1.0 + i) for i in range(n_rows)]
    df = pd.DataFrame(data)
    return df.to_csv(index=False).encode("utf-8")


# ===========================================================================
# 1. Header Collisions and Deduplication Sweep
# ===========================================================================
class TestHeaderSanitizationCollisions:
    """Verify two-way and three-way header formula sanitization collisions."""

    @pytest.mark.parametrize("endpoint,make_payload", [
        ("/api/v1/upload", _make_upload_csv),
        ("/api/v1/forecast", _make_forecast_csv),
        ("/api/v1/hypotheses", _make_hypo_csv),
    ])
    def test_two_way_collision_controlled_and_deduped(self, endpoint: str, make_payload):
        """Headers '=a' and ''=a' must never produce 500 and must be unique and sanitized."""
        csv_bytes = make_payload(["=a", "'=a"])
        res = client.post(
            endpoint,
            files={"file": ("collision2.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"} if endpoint != "/api/v1/upload" else {},
        )
        assert res.status_code == 200, f"{endpoint} returned {res.status_code}: {res.text}"
        payload = res.json()
        violations = inspect_strings_for_raw_formulas(payload)
        assert violations == [], f"Formula leaks in response: {violations}"

        # Check unique headers
        if endpoint == "/api/v1/upload":
            col_names = [c["name"] for c in payload["columns"]]
            assert len(col_names) == len(set(col_names))
            assert any(c.startswith("''=a") or c == "'=a.1" for c in col_names)
        elif endpoint == "/api/v1/forecast":
            assert payload["status"] == "ok"
        elif endpoint == "/api/v1/hypotheses":
            assert payload["status"] == "ok"

    @pytest.mark.parametrize("endpoint,make_payload", [
        ("/api/v1/upload", _make_upload_csv),
        ("/api/v1/forecast", _make_forecast_csv),
        ("/api/v1/hypotheses", _make_hypo_csv),
    ])
    def test_three_way_collision_controlled_and_deduped(self, endpoint: str, make_payload):
        """Three-way collision '=a', ''=a', ''''=a' must be unique, sanitized, and HTTP 200."""
        csv_bytes = make_payload(["=a", "'=a", "''=a"])
        res = client.post(
            endpoint,
            files={"file": ("collision3.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"} if endpoint != "/api/v1/upload" else {},
        )
        assert res.status_code == 200, f"{endpoint} returned {res.status_code}: {res.text}"
        payload = res.json()
        violations = inspect_strings_for_raw_formulas(payload)
        assert violations == [], f"Formula leaks in response: {violations}"

        if endpoint == "/api/v1/upload":
            col_names = [c["name"] for c in payload["columns"]]
            assert len(col_names) == len(set(col_names))


# ===========================================================================
# 2. Leading Whitespace and Full-Width Unicode Formulas
# ===========================================================================
class TestWhitespaceAndUnicodeFormulaInjection:
    """Verify whitespace-prefixed and full-width formula injections."""

    @pytest.mark.parametrize("prefix", [
        " ",
        "\t",
        "\r",
        "\n",
        "  \t\r\n",
    ])
    @pytest.mark.parametrize("formula_char", ["=", "+", "-", "@"])
    def test_whitespace_prefixed_formula_in_cells_and_headers(self, prefix: str, formula_char: str):
        """Whitespace before formula char in headers and cells must be neutralized with a leading quote."""
        cell_val = f"{prefix}{formula_char}cmd|' /C calc'!A0"
        header_val = f"{prefix}{formula_char}metric"

        df = pd.DataFrame({
            "date": ["2020-01-01", "2020-01-02"],
            header_val: [10.5, 11.2],
            "label": [cell_val, "normal_val"],
        })
        csv_content = df.to_csv(index=False).encode("utf-8")

        res = client.post(
            "/api/v1/upload",
            files={"file": ("whitespace_formula.csv", csv_content, "text/csv")},
        )
        assert res.status_code == 200
        payload = res.json()
        violations = inspect_strings_for_raw_formulas(payload)
        assert violations == [], f"Formula leaks: {violations}"

    @pytest.mark.parametrize("full_width_char", ["\uff1d", "\uff0d", "\uff0b", "\uff20"])
    def test_full_width_unicode_formulas_neutralized(self, full_width_char: str):
        """Full-width unicode formula symbols must be neutralized."""
        header_val = f"{full_width_char}calc"
        cell_val = f"  {full_width_char}SUM(1+1)"

        csv_content = (
            f"date,{header_val},notes\n"
            f"2020-01-01,100.0,{cell_val}\n"
            f"2020-01-02,105.0,test\n"
        ).encode("utf-8")

        for endpoint in ["/api/v1/upload", "/api/v1/hypotheses"]:
            res = client.post(
                endpoint,
                files={"file": ("unicode_formula.csv", csv_content, "text/csv")},
                data={"use_llm": "false"} if endpoint != "/api/v1/upload" else {},
            )
            assert res.status_code == 200
            violations = inspect_strings_for_raw_formulas(res.json())
            assert violations == [], f"{endpoint} leaked full-width formula: {violations}"


# ===========================================================================
# 3. Headers That Are Only Dangerous Prefixes or Empty
# ===========================================================================
class TestDangerousPrefixOnlyAndEmptyHeaders:
    """Verify headers that consist only of dangerous prefix characters or empty strings."""

    @pytest.mark.parametrize("endpoint", ["/api/v1/upload", "/api/v1/forecast", "/api/v1/hypotheses"])
    def test_prefix_only_headers_handled_safely(self, endpoint: str):
        """Headers '=', '+', '-', '@' must be neutralized and unique without producing 500."""
        csv_bytes = _make_forecast_csv(["=", "+", "-", "@"], n_rows=35)
        res = client.post(
            endpoint,
            files={"file": ("prefix_only.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"} if endpoint != "/api/v1/upload" else {},
        )
        assert res.status_code == 200
        payload = res.json()
        violations = inspect_strings_for_raw_formulas(payload)
        assert violations == [], f"Leaked prefix in {endpoint}: {violations}"

    def test_empty_headers_handled_safely(self):
        """Empty column headers parse cleanly without crashing."""
        csv_bytes = b",,val\n1,2,3\n4,5,6\n"
        res = client.post(
            "/api/v1/upload",
            files={"file": ("empty_headers.csv", csv_bytes, "text/csv")},
        )
        assert res.status_code == 200
        payload = res.json()
        col_names = [c["name"] for c in payload["columns"]]
        assert len(col_names) == len(set(col_names))


# ===========================================================================
# 4. Filename Security and Zero Server Path Leakage
# ===========================================================================
class TestFilenameSecurityAndNoPathLeakage:
    """Validate path traversals, null bytes, long names, and backslashes."""

    @pytest.mark.parametrize("endpoint", ["/api/v1/upload", "/api/v1/forecast", "/api/v1/hypotheses"])
    def test_path_traversal_filename_never_leaked(self, endpoint: str):
        """Path traversal '../../x.csv' must never appear in response success or error bodies."""
        csv_bytes = _make_forecast_csv(["sales"], n_rows=35)
        res = client.post(
            endpoint,
            files={"file": ("../../secret/x.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"} if endpoint != "/api/v1/upload" else {},
        )
        assert res.status_code in (200, 400, 415, 422)
        body = res.text
        assert "../../" not in body
        assert "secret" not in body

    @pytest.mark.parametrize("endpoint", ["/api/v1/upload", "/api/v1/forecast", "/api/v1/hypotheses"])
    def test_backslash_path_never_leaked(self, endpoint: str):
        """Windows backslash path '..\\..\\secret\\x.csv' must not leak directory traversal in response."""
        csv_bytes = _make_forecast_csv(["sales"], n_rows=35)
        res = client.post(
            endpoint,
            files={"file": ("..\\..\\secret\\x.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"} if endpoint != "/api/v1/upload" else {},
        )
        assert res.status_code in (200, 400, 415, 422)
        body = res.text
        assert "..\\" not in body
        assert "secret" not in body

    @pytest.mark.parametrize("endpoint", ["/api/v1/upload", "/api/v1/forecast", "/api/v1/hypotheses"])
    def test_null_byte_in_filename_rejected(self, endpoint: str):
        """Literal null byte and %00 URL-encoded null byte in filename rejected with 4xx, never 500."""
        csv_bytes = _make_forecast_csv(["sales"], n_rows=35)

        for bad_name in ["test\x00.csv", "test%00.csv"]:
            res = client.post(
                endpoint,
                files={"file": (bad_name, csv_bytes, "text/csv")},
                data={"use_llm": "false"} if endpoint != "/api/v1/upload" else {},
            )
            assert res.status_code in (400, 415)
            assert "Traceback" not in res.text
            assert "null byte" in res.text.lower()

    @pytest.mark.parametrize("endpoint", ["/api/v1/upload", "/api/v1/forecast", "/api/v1/hypotheses"])
    def test_long_filename_handled_without_crash(self, endpoint: str):
        """A 5,000-character filename is handled gracefully without unhandled 500."""
        csv_bytes = _make_forecast_csv(["sales"], n_rows=35)
        long_name = ("a" * 5000) + ".csv"
        res = client.post(
            endpoint,
            files={"file": (long_name, csv_bytes, "text/csv")},
            data={"use_llm": "false"} if endpoint != "/api/v1/upload" else {},
        )
        assert res.status_code in (200, 400, 415, 422)
        assert "Traceback" not in res.text


# ===========================================================================
# 5. Finding 3 Equivalent: Controlled Internal Exception Handling & GC
# ===========================================================================
class TestInternalExceptionHandlingAndGC:
    """Force unexpected runtime exceptions in forecast and hypotheses; confirm controlled 500 and GC."""

    def test_forecast_unexpected_exception_controlled_and_gc_runs(self):
        """Unexpected non-ValueError in forecast produces controlled 500 and triggers gc.collect()."""
        csv_bytes = _make_forecast_csv(["sales"], n_rows=35)

        with patch("src.api.analytics_router.run_forecast", side_effect=RuntimeError("Kernel forecast computation fault")), \
             patch("src.api.analytics_router.gc.collect") as mock_gc:

            res = client.post(
                "/api/v1/forecast",
                files={"file": ("test_forecast.csv", csv_bytes, "text/csv")},
                data={"use_llm": "false"},
            )
            assert res.status_code == 500
            body = res.text
            assert "Traceback (most recent call last)" not in body
            assert "Forecast computation error: RuntimeError" in body
            assert mock_gc.called, "gc.collect() was not invoked in forecast finally block"

    def test_hypotheses_unexpected_exception_controlled_and_gc_runs(self):
        """Unexpected non-ValueError in hypotheses produces controlled 500 and triggers gc.collect()."""
        csv_bytes = _make_hypo_csv(["metric"], n_rows=35)

        with patch("src.api.analytics_router.run_hypotheses", side_effect=RuntimeError("Kernel hypothesis computation fault")), \
             patch("src.api.analytics_router.gc.collect") as mock_gc:

            res = client.post(
                "/api/v1/hypotheses",
                files={"file": ("test_hypo.csv", csv_bytes, "text/csv")},
                data={"use_llm": "false"},
            )
            assert res.status_code == 500
            body = res.text
            assert "Traceback (most recent call last)" not in body
            assert "Hypothesis computation error: RuntimeError" in body
            assert mock_gc.called, "gc.collect() was not invoked in hypotheses finally block"
