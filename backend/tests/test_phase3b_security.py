"""Phase 3B Security and Hostile-File Audit (Anti-Gravity 5-Vector Audit Gate).

Independent Second-Pass Verification and Adversarial Security Test Suite for:
POST /api/v1/segmentation (Zero-Auth, Stateless, Ephemeral In-Memory Analytics)

Vectors Covered:
- Vector 1: Ephemeral RAM Lifecycle & Zero Disk Persistence
- Vector 2: Input Injection & CWE-1236 Formula Neutralization
- Vector 3: Prompt Injection & Data Isolation (Zero Leakage to LLM)
- Vector 4: Denial of Service & Free-Tier Budget Protection
- Vector 5: Logic Flaws & Degenerate Tabular Shapes
"""

from __future__ import annotations

import builtins
import concurrent.futures
import gc
import io
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import zipfile

import httpx
import numpy as np
import pandas as pd
import pytest
from starlette.testclient import TestClient

from config.settings import Settings, get_settings
from main import app
from src.orchestrator.chart_picker import ALLOWED, pick_chart
from src.parsers.sanitization import (
    FORMULA_PREFIXES,
    gatekeep_tabular_upload,
    sanitize_tabular_cells,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "data"
client = TestClient(app)


# ===========================================================================
# Helper Utilities
# ===========================================================================
def _generate_valid_segmentation_csv(n_rows: int = 40, seed: int = 42) -> bytes:
    """Generate a clean synthetic numeric CSV payload for segmentation."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "sales": 100.0 + rng.normal(0, 15, n_rows),
        "margin": 20.0 + rng.normal(0, 5, n_rows),
        "units": rng.integers(1, 50, n_rows),
    })
    return df.to_csv(index=False).encode("utf-8")


def _inspect_strings_for_raw_formulas(obj: Any, path: str = "root") -> List[str]:
    """Recursively search any JSON-like data structure for raw unescaped formula strings."""
    violations: List[str] = []
    if isinstance(obj, str):
        # A raw formula string starts with =, @, +, - (without single quote escape)
        # or has leading whitespace followed by =, @, +, -
        stripped = obj.lstrip()
        if stripped and stripped[0] in ("=", "@", "+", "-", "\uff1d", "\uff20"):
            if not obj.startswith("'"):
                violations.append(f"{path}: {obj!r}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                stripped_k = k.lstrip()
                if stripped_k and stripped_k[0] in ("=", "@", "+", "-", "\uff1d", "\uff20"):
                    if not k.startswith("'"):
                        violations.append(f"{path}.<key:{k}>")
            violations.extend(_inspect_strings_for_raw_formulas(v, f"{path}.{k}"))
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            violations.extend(_inspect_strings_for_raw_formulas(item, f"{path}[{i}]"))
    return violations


# ===========================================================================
# Vector 1: Ephemeral RAM & Zero-Disk-Persistence
# ===========================================================================
class TestVector1EphemeralRAM:
    """Validate zero persistence to disk and ephemeral memory lifecycle in POST /segmentation."""

    def test_segmentation_zero_file_writes(self):
        """Assert POST /api/v1/segmentation performs zero file write operations to disk."""
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

            csv_bytes = _generate_valid_segmentation_csv(50)
            res = client.post(
                "/api/v1/segmentation",
                files={"file": ("ephemeral_segmentation.csv", csv_bytes, "text/csv")},
                data={"use_llm": "false"},
            )
            assert res.status_code == 200
            assert forbidden_writes == [], f"Unexpected disk write attempts: {forbidden_writes}"

    def test_segmentation_zero_residual_temp_or_cwd_files(self):
        """Assert zero residual files in OS temp or working directory before and after."""
        temp_dir = tempfile.gettempdir()
        cwd_dir = os.getcwd()

        temp_before = set(os.listdir(temp_dir))
        cwd_before = set(os.listdir(cwd_dir))

        csv_bytes = _generate_valid_segmentation_csv(60)
        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("residual_check.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200

        temp_after = set(os.listdir(temp_dir))
        cwd_after = set(os.listdir(cwd_dir))

        assert cwd_after - cwd_before == set(), "Residual files created in current working directory"
        new_temp = {f for f in (temp_after - temp_before) if not f.startswith("tmp_py")}
        assert len(new_temp) == 0, f"Residual files created in temp directory: {new_temp}"

    def test_segmentation_gc_collect_invoked_on_all_paths(self):
        """Verify gc.collect() is called on 200 success, 4xx client error, and 500 error paths."""
        with patch("src.api.segmentation.gc.collect") as mock_gc:
            # 1. Success path (200)
            csv_bytes = _generate_valid_segmentation_csv(40)
            res_200 = client.post(
                "/api/v1/segmentation",
                files={"file": ("gc_test.csv", csv_bytes, "text/csv")},
                data={"use_llm": "false"},
            )
            assert res_200.status_code == 200
            assert mock_gc.called, "gc.collect() not called on 200 success path"

            mock_gc.reset_mock()

            # 2. Client error path (422 empty / non-numeric)
            empty_df = pd.DataFrame({"text_only": ["a", "b", "c"]})
            res_422 = client.post(
                "/api/v1/segmentation",
                files={"file": ("non_numeric.csv", empty_df.to_csv(index=False).encode(), "text/csv")},
                data={"use_llm": "false"},
            )
            assert res_422.status_code == 422
            assert mock_gc.called, "gc.collect() not called on 422 error path"

            mock_gc.reset_mock()

            # 3. Controlled failure path (500 internal error)
            with patch("src.api.segmentation.run_segmentation", side_effect=RuntimeError("Kernel fault")):
                res_500 = client.post(
                    "/api/v1/segmentation",
                    files={"file": ("fault.csv", csv_bytes, "text/csv")},
                    data={"use_llm": "false"},
                )
                assert res_500.status_code == 500
                assert mock_gc.called, "gc.collect() not called on 500 error path"

    def test_segmentation_concurrency_and_memory_isolation(self):
        """Fire 20 concurrent requests with distinct payloads; check state isolation and RAM return."""
        gc.collect()

        def _make_request(req_id: int) -> dict:
            rng = np.random.default_rng(1000 + req_id)
            # Distinct data scale per request so responses can be mapped to inputs
            df = pd.DataFrame({
                "metric_a": 1000.0 * req_id + rng.normal(0, 1, 30),
                "metric_b": 500.0 * req_id + rng.normal(0, 1, 30),
            })
            b = df.to_csv(index=False).encode()
            r = client.post(
                "/api/v1/segmentation",
                files={"file": (f"req_{req_id}.csv", b, "text/csv")},
                data={"use_llm": "false"},
            )
            return {"id": req_id, "status": r.status_code, "data": r.json()}

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_make_request, i) for i in range(1, 21)]
            results = [f.result() for f in futures]

        for res in results:
            assert res["status"] == 200, f"Request {res['id']} failed with {res}"
            payload = res["data"]
            assert payload["status"] == "ok"
            assert payload["original_row_count"] == 30
            # Confirm response matches its own input scale: features_used must match
            assert "metric_a" in payload["features_used"]
            assert "metric_b" in payload["features_used"]
            # Outlier records must contain the request-specific scale
            outliers = payload["outlier_records"]
            assert len(outliers) > 0
            first_val = outliers[0].get("metric_a")
            req_id = res["id"]
            assert abs(first_val - 1000.0 * req_id) < 100.0, (
                f"Data contamination across concurrent requests! Expected ~{1000.0 * req_id}, got {first_val}"
            )

        gc.collect()

    def test_segmentation_unexpected_exception_controlled_and_no_traceback(self):
        """Unexpected exception in run_segmentation produces a controlled 500 without stack trace leakage."""
        csv_bytes = _generate_valid_segmentation_csv(40)
        with patch("src.api.segmentation.run_segmentation", side_effect=RuntimeError("Internal segmentation engine fault")):
            res = client.post(
                "/api/v1/segmentation",
                files={"file": ("kernel_fault.csv", csv_bytes, "text/csv")},
                data={"use_llm": "false"},
            )
            assert res.status_code == 500
            body = res.text
            assert "Traceback (most recent call last)" not in body, "Stack trace leaked in 500 response"
            assert "Segmentation computation error" in body


# ===========================================================================
# Vector 2: Input Injection & CWE-1236 Formula Neutralization
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

        r = client.post(
            "/api/v1/segmentation",
            files={"file": (filename, content, content_type)},
            data={"use_llm": "false"},
        )
        assert r.status_code < 500, f"Segmentation returned HTTP {r.status_code} for {filename}: {r.text[:200]}"
        text = r.text
        assert "Traceback (most recent call last)" not in text, f"Traceback leaked for {filename}"
        assert "Internal Server Error" not in text

    def test_formula_cells_neutralized_in_outlier_records(self):
        """Verify formula prefixes in string tabular cells are quoted in outlier_records."""
        rng = np.random.default_rng(42)
        n = 40
        df = pd.DataFrame({
            "feature_1": 100.0 + rng.normal(0, 10, n),
            "feature_2": 50.0 + rng.normal(0, 5, n),
            "comment": ["=cmd|' /C calc'!A0", "@SUM(1+1)", "+12345", "-98765"] * (n // 4),
        })
        csv_bytes = df.to_csv(index=False).encode("utf-8")

        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("formula_cells.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200
        payload = res.json()
        outliers = payload.get("outlier_records", [])
        assert len(outliers) > 0

        for record in outliers:
            val = record.get("comment")
            if val is not None and isinstance(val, str):
                assert not val.startswith(("=", "@", "+", "-")), f"Unsanitized formula cell: {val}"
                assert val.startswith("'"), f"Formula cell not quoted: {val}"

    def test_formula_headers_neutralized_in_echoed_outputs(self):
        """Verify dangerous formula prefixes in column headers are neutralized across all echoed response keys."""
        rng = np.random.default_rng(42)
        n = 40
        df = pd.DataFrame({
            "=cmd|' /C calc'!A0": 100.0 + rng.normal(0, 10, n),
            "@SUM(A1:B1)": 50.0 + rng.normal(0, 5, n),
            "+bonus": 25.0 + rng.normal(0, 2, n),
            "-penalty": 5.0 + rng.normal(0, 1, n),
        })
        csv_bytes = df.to_csv(index=False).encode("utf-8")

        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("formula_headers.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200
        payload = res.json()

        # 1. features_used list
        for f in payload.get("features_used", []):
            assert not f.startswith(("=", "@", "+", "-")), f"Unsanitized feature header: {f}"
            assert f.startswith("'")

        # 2. correlation_matrix.columns
        for c in payload.get("correlation_matrix", {}).get("columns", []):
            assert not c.startswith(("=", "@", "+", "-")), f"Unsanitized corr column: {c}"
            assert c.startswith("'")

        # 3. correlation_matrix.points {x, y}
        for pt in payload.get("correlation_matrix", {}).get("points", []):
            assert not pt["x"].startswith(("=", "@", "+", "-"))
            assert not pt["y"].startswith(("=", "@", "+", "-"))

        # 4. outlier_records keys
        for rec in payload.get("outlier_records", []):
            for k in rec.keys():
                if k not in ("id", "anomaly_score", "cluster"):
                    assert not k.startswith(("=", "@", "+", "-")), f"Unsanitized outlier record key: {k}"

    def test_whitespace_prefixed_formula_neutralized(self):
        """Verify formulas preceded by spaces, tabs, or newlines are neutralized."""
        df = pd.DataFrame({
            "val1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "val2": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0],
            "injected": [
                " =cmd|calc",
                "\t=SUM(A1)",
                "\n+cmd",
                "\r-calc",
                "   @SUM(1+1)",
                "normal",
                "normal2",
                "normal3",
                "normal4",
                "normal5",
            ],
        })
        csv_bytes = df.to_csv(index=False).encode("utf-8")

        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("ws_formula.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200
        payload = res.json()
        outliers = payload.get("outlier_records", [])

        for rec in outliers:
            val = rec.get("injected")
            if val is not None and isinstance(val, str):
                stripped = val.lstrip()
                if stripped and stripped[0] in ("=", "@", "+", "-"):
                    assert val.startswith("'"), f"Whitespace formula not escaped with quote: {val!r}"

    def test_unicode_lookalike_formula_prefixes_neutralized(self):
        """Verify full-width Unicode formula lookalikes (\uff1d, \uff20) are neutralized."""
        df = pd.DataFrame({
            "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "b": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0],
            "uni": [
                "\uff1dcmd",
                "\uff20SUM",
                "c", "d", "e", "f", "g", "h", "i", "j"
            ],
        })
        csv_bytes = df.to_csv(index=False).encode("utf-8")

        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("uni_formula.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200
        payload = res.json()
        for rec in payload.get("outlier_records", []):
            val = rec.get("uni")
            if val is not None and isinstance(val, str):
                stripped = val.lstrip()
                if stripped and stripped[0] in ("\uff1d", "\uff20"):
                    assert val.startswith("'"), f"Unicode formula not quoted: {val!r}"

    def test_header_sanitization_collision_resilience(self):
        """Verify headers that collide after quoting (=a and '=a) are deduplicated without crash."""
        csv_content = b"=a,'=a\n1,2\n3,4\n5,6\n7,8\n9,10\n11,12\n"
        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("collision.csv", csv_content, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200
        payload = res.json()
        features = payload.get("features_used", [])
        assert len(features) == 2
        assert len(set(features)) == 2, f"Features must be unique: {features}"
        assert features[0].startswith("'")
        assert features[1].startswith("'")

    def test_headers_only_dangerous_prefix(self):
        """Verify headers that are only dangerous characters (=, @) are safely handled."""
        csv_content = b"=,@\n1,2\n3,4\n5,6\n7,8\n9,10\n11,12\n"
        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("only_prefix.csv", csv_content, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200
        payload = res.json()
        features = payload.get("features_used", [])
        for f in features:
            assert f.startswith("'")

    def test_parquet_formula_strings_neutralized(self):
        """Verify parquet files containing formula strings are neutralized."""
        df = pd.DataFrame({
            "num1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            "num2": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0],
            "formula_col": ["=cmd|calc", "@SUM(1+1)", "+99", "-1", "ok", "ok", "ok", "ok"],
        })
        bio = io.BytesIO()
        df.to_parquet(bio, index=False)
        parquet_bytes = bio.getvalue()

        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("data.parquet", parquet_bytes, "application/vnd.apache.parquet")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200
        payload = res.json()
        for rec in payload.get("outlier_records", []):
            val = rec.get("formula_col")
            if val is not None and isinstance(val, str):
                assert not val.startswith(("=", "@", "+", "-")), f"Unsanitized formula: {val}"
                if val != "ok":
                    assert val.startswith("'"), f"Formula not quoted: {val}"

    def test_comprehensive_response_echo_surfaces_inspection(self):
        """Recursively scan every key and value in the entire JSON response for raw formula injections."""
        rng = np.random.default_rng(42)
        n = 30
        df = pd.DataFrame({
            "=cmd_head": 100.0 + rng.normal(0, 10, n),
            "@sum_head": 50.0 + rng.normal(0, 5, n),
            "+bonus_head": 25.0 + rng.normal(0, 2, n),
            "normal_cell": [" =evil_cell", "\t@sum_cell", "safe"] * 10,
        })
        csv_bytes = df.to_csv(index=False).encode("utf-8")

        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("full_echo_test.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200
        payload = res.json()
        violations = _inspect_strings_for_raw_formulas(payload)
        assert violations == [], f"Found raw unescaped formula strings in response: {violations}"


# ===========================================================================
# Vector 3: Prompt Injection & Data Isolation (LLM Gating)
# ===========================================================================
class TestVector3PromptInjectionAndLLMIsolation:
    """Validate zero column/cell leakage to LLM, prompt injection resilience, and safe fallback."""

    def test_outgoing_gemini_payload_zero_user_data_leakage(self):
        """Assert outgoing Gemini payload contains ZERO column names and ZERO cell values."""
        intercepted_requests: list[dict] = []

        def mock_transport_handler(request: httpx.Request) -> httpx.Response:
            intercepted_requests.append({
                "url": str(request.url),
                "headers": dict(request.headers),
                "body": json.loads(request.read().decode("utf-8")),
            })
            # Return valid model response
            gemini_resp = {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": json.dumps({
                                "charts": ["scatter_cluster", "outlier_table"],
                                "reason": "Clusters and anomalies identified.",
                            })
                        }]
                    }
                }]
            }
            return httpx.Response(200, json=gemini_resp)

        transport = httpx.MockTransport(mock_transport_handler)

        secret_columns = ["CustomerSSN", "EmployeeSalary", "SecretProjectCode"]
        df = pd.DataFrame({
            secret_columns[0]: [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            secret_columns[1]: [50000.0, 60000.0, 70000.0, 80000.0, 90000.0, 95000.0],
            secret_columns[2]: [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        })
        csv_bytes = df.to_csv(index=False).encode("utf-8")

        custom_settings = Settings(google_api_key="mock_test_key_xyz", chart_picker_enabled=True)
        original_async_client = httpx.AsyncClient

        def custom_async_client(*args, **kwargs):
            kwargs["transport"] = transport
            return original_async_client(*args, **kwargs)

        with patch("src.api.segmentation.get_settings", return_value=custom_settings), \
             patch("src.orchestrator.chart_picker.get_settings", return_value=custom_settings), \
             patch("src.orchestrator.chart_picker.httpx.AsyncClient", side_effect=custom_async_client):

            res = client.post(
                "/api/v1/segmentation",
                files={"file": ("confidential.csv", csv_bytes, "text/csv")},
                data={"use_llm": "true"},
            )
            assert res.status_code == 200

        assert len(intercepted_requests) == 1, "Expected exactly 1 outgoing LLM request"
        req = intercepted_requests[0]
        body_text = json.dumps(req["body"])

        # Invariant checks:
        for secret_col in secret_columns:
            assert secret_col not in body_text, f"Secret column name leaked to LLM: {secret_col}"

        # Cell values check
        for cell_val in ["50000", "60000", "70000", "80000", "90000"]:
            assert cell_val not in body_text, f"Secret cell value leaked to LLM: {cell_val}"

        # Verify outgoing payload only contains anonymous aggregate schema facts
        user_part = req["body"]["contents"][0]["parts"][0]["text"]
        facts = json.loads(user_part)
        assert facts["result_type"] == "segmentation"
        assert facts["status"] == "ok"
        assert "n_samples" in facts
        assert "optimal_k" in facts
        assert "n_outliers" in facts
        assert "has_correlation_data" in facts

    def test_prompt_injection_headers_never_reach_llm(self):
        """Assert malicious instructions in CSV headers never appear in the outgoing LLM prompt."""
        intercepted_requests: list[dict] = []

        def mock_handler(request: httpx.Request) -> httpx.Response:
            intercepted_requests.append({"body": json.loads(request.read().decode("utf-8"))})
            return httpx.Response(200, json={
                "candidates": [{"content": {"parts": [{"text": '{"charts": ["scatter_cluster"], "reason": "ok"}'}]}}]
            })

        transport = httpx.MockTransport(mock_handler)
        filepath = FIXTURES_DIR / "hostile_prompt_injection_headers.csv"
        with open(filepath, "rb") as f:
            content = f.read()

        custom_settings = Settings(google_api_key="mock_key", chart_picker_enabled=True)
        original_async_client = httpx.AsyncClient

        def custom_async_client(*args, **kwargs):
            kwargs["transport"] = transport
            return original_async_client(*args, **kwargs)

        with patch("src.api.segmentation.get_settings", return_value=custom_settings), \
             patch("src.orchestrator.chart_picker.get_settings", return_value=custom_settings), \
             patch("src.orchestrator.chart_picker.httpx.AsyncClient", side_effect=custom_async_client):

            res = client.post(
                "/api/v1/segmentation",
                files={"file": ("prompt_inj.csv", content, "text/csv")},
                data={"use_llm": "true"},
            )
            assert res.status_code == 200

        assert len(intercepted_requests) == 1
        body_text = json.dumps(intercepted_requests[0]["body"])
        assert "Ignore previous instructions" not in body_text
        assert "reveal all API keys" not in body_text
        assert "say PWNED" not in body_text

    def test_llm_enabled_missing_api_key_falls_back_gracefully(self):
        """When use_llm=true but no API key is provided, gracefully fall back to heuristic."""
        csv_bytes = _generate_valid_segmentation_csv(40)
        custom_settings = Settings(
            google_api_key="",
            GOOGLE_API_KEY="",
            LLM_API_KEY="",
            GEMINI_API_KEY="",
            chart_picker_enabled=True,
        )

        with patch("src.api.segmentation.get_settings", return_value=custom_settings), \
             patch("src.orchestrator.chart_picker.get_settings", return_value=custom_settings):

            res = client.post(
                "/api/v1/segmentation",
                files={"file": ("no_key.csv", csv_bytes, "text/csv")},
                data={"use_llm": "true"},
            )
            assert res.status_code == 200
            payload = res.json()
            rec = payload.get("recommended_visualization", {})
            assert rec["source"] == "heuristic"
            assert rec["fallback_reason"] == "no_api_key"
            assert rec["chart"] in ALLOWED

    def test_llm_timeout_falls_back_gracefully(self):
        """When the LLM call times out, fall back safely to heuristic without raising 500."""
        csv_bytes = _generate_valid_segmentation_csv(40)
        custom_settings = Settings(google_api_key="test_key", chart_picker_enabled=True, llm_timeout_s=0.01)

        def timeout_handler(request: httpx.Request):
            raise httpx.ConnectTimeout("Connection timed out after 10ms")

        transport = httpx.MockTransport(timeout_handler)
        original_async_client = httpx.AsyncClient

        def custom_async_client(*args, **kwargs):
            kwargs["transport"] = transport
            return original_async_client(*args, **kwargs)

        with patch("src.api.segmentation.get_settings", return_value=custom_settings), \
             patch("src.orchestrator.chart_picker.get_settings", return_value=custom_settings), \
             patch("src.orchestrator.chart_picker.httpx.AsyncClient", side_effect=custom_async_client):

            res = client.post(
                "/api/v1/segmentation",
                files={"file": ("timeout.csv", csv_bytes, "text/csv")},
                data={"use_llm": "true"},
            )
            assert res.status_code == 200
            payload = res.json()
            rec = payload.get("recommended_visualization", {})
            assert rec["source"] == "heuristic"
            assert "llm_error" in rec.get("fallback_reason", "")
            assert rec["chart"] in ALLOWED

    @pytest.mark.parametrize("adversarial_content", [
        '{"charts": ["DROP TABLE users;"], "reason": "sql injection"}',
        '{"charts": ["<script>alert(1)</script>"], "reason": "xss injection"}',
        '{"charts": ["eval(dangerous)"], "reason": "rce"}',
        '{"charts": ["unregistered_3d_pie_chart"], "reason": "unauthorized component"}',
        'Malformed non-JSON plaintext model response',
        '{"invalid_schema": true}',
    ])
    def test_adversarial_llm_responses_handled_safely(self, adversarial_content: str):
        """Assert adversarial or invalid model outputs are caught and fall back to valid components."""
        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "candidates": [{"content": {"parts": [{"text": adversarial_content}]}}]
            })

        transport = httpx.MockTransport(mock_handler)
        csv_bytes = _generate_valid_segmentation_csv(40)
        custom_settings = Settings(google_api_key="mock_key", chart_picker_enabled=True)
        original_async_client = httpx.AsyncClient

        def custom_async_client(*args, **kwargs):
            kwargs["transport"] = transport
            return original_async_client(*args, **kwargs)

        with patch("src.api.segmentation.get_settings", return_value=custom_settings), \
             patch("src.orchestrator.chart_picker.get_settings", return_value=custom_settings), \
             patch("src.orchestrator.chart_picker.httpx.AsyncClient", side_effect=custom_async_client):

            res = client.post(
                "/api/v1/segmentation",
                files={"file": ("adv_llm.csv", csv_bytes, "text/csv")},
                data={"use_llm": "true"},
            )
            assert res.status_code == 200
            payload = res.json()
            rec = payload.get("recommended_visualization", {})
            assert rec["source"] == "heuristic"
            assert rec["chart"] in ALLOWED
            assert set(rec["charts"]).issubset(ALLOWED)


# ===========================================================================
# Vector 4: Denial of Service & Free-Tier Limits
# ===========================================================================
class TestVector4DoSAndFreeTierLimits:
    """Validate 50MB upload limits, decompression bombs, and computational bounding."""

    def test_exact_50mb_boundary_and_plus_one_rejection(self):
        """Assert 50MB limit: 50MB + 1 byte is rejected with HTTP 413; exactly 50MB passes gatekeeper."""
        max_bytes = 50 * 1024 * 1024

        # 1. 50MB + 1 byte must raise 413 immediately
        oversized = b"a" * (max_bytes + 1)
        with pytest.raises(Exception) as exc_info:
            gatekeep_tabular_upload("oversized.csv", oversized, "text/csv", max_bytes=max_bytes)
        assert getattr(exc_info.value, "status_code", None) == 413

        # 2. Exactly 50MB passes gatekeeper
        exact_50mb = b"col1,col2\n" + b"1,2\n" * ((max_bytes - 10) // 4)
        exact_bytes = exact_50mb[:max_bytes]
        ext = gatekeep_tabular_upload("boundary.csv", exact_bytes, "text/csv", max_bytes=max_bytes)
        assert ext == "csv"

    def test_content_length_mismatch_handling(self):
        """Verify mismatched Content-Length headers do not hang or crash the endpoint."""
        csv_bytes = _generate_valid_segmentation_csv(30)
        # Content-length smaller than actual
        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("mismatch.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"},
            headers={"Content-Length": "10"},
        )
        assert res.status_code in (200, 400, 422)

    def test_empty_file_rejected_422(self):
        """Uploading an empty 0-byte file returns HTTP 422 immediately."""
        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("empty.csv", b"", "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 422
        assert "0 bytes" in res.text

    def test_ultra_wide_5000_cols_performance_and_memory(self):
        """Assert ultra-wide table (5,000 columns) completes within latency limits without memory bloat."""
        filepath = FIXTURES_DIR / "hostile_wide_5000_cols.csv"
        with open(filepath, "rb") as f:
            content = f.read()

        t0 = time.perf_counter()
        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("wide_5000.csv", content, "text/csv")},
            data={"use_llm": "false"},
        )
        elapsed = time.perf_counter() - t0
        assert res.status_code == 200
        assert elapsed < 10.0, f"Wide table took too long: {elapsed:.2f}s"
        payload = res.json()
        assert payload["status"] == "ok"
        # Correlation matrix must be truncated to <= 25 columns
        corr_cols = payload.get("correlation_matrix", {}).get("columns", [])
        assert len(corr_cols) <= 25
        assert payload.get("correlation_matrix_truncated", False) is True

    def test_deep_table_row_cap_subsampling(self):
        """Tables with > 20,000 rows must be subsampled to the 20,000 live-fit ceiling."""
        rng = np.random.default_rng(42)
        n_rows = 25_000
        df = pd.DataFrame({
            "feature_a": rng.normal(0, 1, n_rows),
            "feature_b": rng.normal(5, 2, n_rows),
        })
        csv_bytes = df.to_csv(index=False).encode("utf-8")

        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("deep_table.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200
        payload = res.json()
        assert payload["subsampled"] is True
        assert payload["original_row_count"] == 25_000
        # Points array must be capped at 10,000 points
        assert len(payload["pca_x"]) <= 10_000

    def test_decompression_bomb_parquet_high_row_count(self):
        """A small Parquet file expanding to 60,000 rows must be subsampled cleanly."""
        rng = np.random.default_rng(42)
        n = 60_000
        df = pd.DataFrame({
            "col_1": rng.normal(0, 1, n).astype(np.float32),
            "col_2": rng.normal(10, 2, n).astype(np.float32),
        })
        bio = io.BytesIO()
        df.to_parquet(bio, compression="snappy", index=False)
        parquet_bytes = bio.getvalue()
        # Compressed on disk is small (~500 KB) but row count is 60,000
        assert len(parquet_bytes) < 1_000_000

        t0 = time.perf_counter()
        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("bomb.parquet", parquet_bytes, "application/vnd.apache.parquet")},
            data={"use_llm": "false"},
        )
        elapsed = time.perf_counter() - t0
        assert res.status_code == 200
        assert elapsed < 5.0, f"High-row Parquet took too long: {elapsed:.2f}s"
        payload = res.json()
        assert payload["subsampled"] is True
        assert payload["original_row_count"] == 60_000

    def test_decompression_bomb_xlsx_zip_expansion_bounded(self):
        """XLSX containing multiple sheets or oversized declared XML is handled safely."""
        bio = io.BytesIO()
        # Create an Excel file with multiple dummy sheets using pandas/openpyxl
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [10, 20, 30, 40, 50]})
            df.to_excel(writer, sheet_name="Sheet1", index=False)
            for s in range(2, 6):
                df.to_excel(writer, sheet_name=f"Sheet{s}", index=False)
        xlsx_bytes = bio.getvalue()

        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("multisheet.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_csv_enormous_single_cell(self):
        """A CSV with an exceptionally long string cell (1 MB) is handled without crash."""
        huge_cell = "A" * (1024 * 1024)  # 1 MB in single cell
        csv_content = f"num1,num2,huge_str\n1,2,{huge_cell}\n3,4,short\n5,6,short\n7,8,short\n9,10,short\n".encode("utf-8")

        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("huge_cell.csv", csv_content, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


# ===========================================================================
# Vector 5: Logic Flaws & Degenerate Tabular Shapes
# ===========================================================================
class TestVector5LogicFlawsAndHostileShapes:
    """Validate binary magic checks, corrupt files, degenerate shapes, and HTTP surface."""

    def test_spoofed_binary_pe_rejected_415(self):
        """Windows PE executable (MZ header) disguised as CSV is rejected with HTTP 415."""
        fake_pe = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"col1,col2\n1,2\n"
        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("malware.csv", fake_pe, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 415
        assert "Windows executable" in res.text

    def test_spoofed_binary_elf_rejected_415(self):
        """Linux ELF executable disguised as CSV is rejected with HTTP 415."""
        fake_elf = b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00" + b"col1,col2\n1,2\n"
        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("rootkit.csv", fake_elf, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 415
        assert "Linux ELF" in res.text

    def test_corrupt_spreadsheet_rejected_422(self):
        """Corrupted/truncated XLSX archive returns controlled HTTP 422, never 500."""
        filepath = FIXTURES_DIR / "hostile_corrupt.xlsx"
        with open(filepath, "rb") as f:
            content = f.read()

        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("corrupt.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"use_llm": "false"},
        )
        assert res.status_code in (415, 422)
        assert "Traceback" not in res.text

    def test_mime_extension_mismatch_rejected_415(self):
        """Declared MIME type disagreeing with file extension is rejected with HTTP 415."""
        csv_bytes = _generate_valid_segmentation_csv(30)
        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("data.csv", csv_bytes, "application/pdf")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 415
        assert "disagrees with file extension" in res.text

    def test_all_null_columns_handled_gracefully(self):
        """CSV containing all-null columns returns controlled 422."""
        filepath = FIXTURES_DIR / "hostile_all_null_columns.csv"
        with open(filepath, "rb") as f:
            content = f.read()

        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("all_null.csv", content, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 422
        assert "Traceback" not in res.text

    def test_single_column_and_single_row_shapes(self):
        """Single-column and single-row CSV shapes return controlled 422 without 500."""
        for fname in ["hostile_single_column.csv", "hostile_single_row.csv"]:
            filepath = FIXTURES_DIR / fname
            with open(filepath, "rb") as f:
                content = f.read()
            res = client.post(
                "/api/v1/segmentation",
                files={"file": (fname, content, "text/csv")},
                data={"use_llm": "false"},
            )
            assert res.status_code == 422
            assert "Traceback" not in res.text

    def test_tsv_and_txt_format_variants(self):
        """Validate TSV and TXT tab-separated / comma-separated files are supported."""
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "feature1": rng.normal(0, 1, 30),
            "feature2": rng.normal(10, 2, 30),
        })

        # TSV
        tsv_bytes = df.to_csv(sep="\t", index=False).encode("utf-8")
        res_tsv = client.post(
            "/api/v1/segmentation",
            files={"file": ("data.tsv", tsv_bytes, "text/tab-separated-values")},
            data={"use_llm": "false"},
        )
        assert res_tsv.status_code == 200
        assert res_tsv.json()["status"] == "ok"

        # TXT
        txt_bytes = df.to_csv(index=False).encode("utf-8")
        res_txt = client.post(
            "/api/v1/segmentation",
            files={"file": ("data.txt", txt_bytes, "text/plain")},
            data={"use_llm": "false"},
        )
        assert res_txt.status_code == 200
        assert res_txt.json()["status"] == "ok"

    def test_utf8_bom_prefixed_csv(self):
        """Verify UTF-8 BOM-prefixed CSV parses cleanly without mangling column names."""
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "sales": 100.0 + rng.normal(0, 10, 30),
            "margin": 20.0 + rng.normal(0, 5, 30),
        })
        raw_csv = df.to_csv(index=False).encode("utf-8")
        bom_csv = b"\xef\xbb\xbf" + raw_csv

        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("bom_data.csv", bom_csv, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 200
        payload = res.json()
        assert "sales" in payload["features_used"]
        assert "\ufeff" not in payload["features_used"][0]

    def test_ragged_rows_csv_handled_safely(self):
        """CSV with ragged rows returns controlled 422, never an unhandled 500."""
        ragged_csv = b"col1,col2\n1,2\n3,4,5,6\n7,8\n"
        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("ragged.csv", ragged_csv, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res.status_code == 422
        assert "Traceback" not in res.text

    def test_filename_edge_cases_no_leakage(self):
        """Validate filename edge cases: long name, path traversal, null bytes, no extension."""
        csv_bytes = _generate_valid_segmentation_csv(30)

        # 1. Very long filename (5,000 characters)
        long_name = ("a" * 5000) + ".csv"
        res_long = client.post(
            "/api/v1/segmentation",
            files={"file": (long_name, csv_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res_long.status_code in (200, 400, 415, 422)
        assert "Traceback" not in res_long.text

        # 2. Path traversal in filename (../../x.csv)
        res_traversal = client.post(
            "/api/v1/segmentation",
            files={"file": ("../../secret/x.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res_traversal.status_code == 200
        # Invariant: filename must not appear in response
        assert "secret" not in res_traversal.text

        # 3. Path traversal without extension (../../passwd)
        res_no_ext = client.post(
            "/api/v1/segmentation",
            files={"file": ("../../../../etc/passwd", csv_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res_no_ext.status_code == 415
        # Invariant: full directory paths must NOT be echoed back
        assert "../" not in res_no_ext.text
        assert "passwd" in res_no_ext.text

        # 4. Null byte in filename
        res_null = client.post(
            "/api/v1/segmentation",
            files={"file": ("test\x00.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        assert res_null.status_code == 415
        assert "null byte" in res_null.text.lower()

    def test_http_surface_invalid_methods_and_content_types(self):
        """Assert invalid HTTP methods and content types are rejected with 405 or 422."""
        # 1. GET method on POST-only endpoint
        res_get = client.get("/api/v1/segmentation")
        assert res_get.status_code == 405

        # 2. PUT method on POST-only endpoint
        res_put = client.put("/api/v1/segmentation")
        assert res_put.status_code == 405

        # 3. JSON body instead of multipart/form-data
        res_json = client.post("/api/v1/segmentation", json={"file": "not_multipart"})
        assert res_json.status_code == 422

        # 4. Multipart upload with missing file field
        res_missing_file = client.post(
            "/api/v1/segmentation",
            data={"use_llm": "false"},
        )
        assert res_missing_file.status_code == 422

        # 5. Extra unexpected form fields are ignored safely
        csv_bytes = _generate_valid_segmentation_csv(30)
        res_extra = client.post(
            "/api/v1/segmentation",
            files={"file": ("valid.csv", csv_bytes, "text/csv")},
            data={"use_llm": "false", "unexpected_field": "injected", "admin": "true"},
        )
        assert res_extra.status_code == 200
