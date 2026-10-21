"""Zero-Retention and Statelessness Test Suite.

Verifies that no uploaded or parsed data (raw, parsed, imputed, row-level derivatives)
survives the request in any process-level structure (Master Spec §1.1).
Validates live DataFrame counts via gc.get_objects() before and after requests
across upload, forecast, hypotheses, and segmentation endpoints.
"""

from __future__ import annotations

import gc
import io
import numpy as np
import pandas as pd
import pytest
from starlette.testclient import TestClient

from main import app
import main


client = TestClient(app)


def _count_live_dataframes() -> int:
    """Force gc and count live pandas DataFrame objects in process memory."""
    gc.collect()
    return sum(1 for obj in gc.get_objects() if isinstance(obj, pd.DataFrame))


def _get_module_container_sizes() -> dict[str, int]:
    """Inspect known module-level container sizes in main and src to detect state retention."""
    sizes: dict[str, int] = {}
    if hasattr(main, "DATA_STORE"):
        ds = getattr(main, "DATA_STORE")
        if isinstance(ds, (dict, list, set)):
            sizes["main.DATA_STORE"] = len(ds)
    return sizes


def _get_rss_mb() -> float:
    """Measure Resident Set Size in MB using Windows API with safe fallback."""
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        fn = ctypes.windll.psapi.GetProcessMemoryInfo
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        fn.restype = wintypes.BOOL
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        if fn(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            return pmc.WorkingSetSize / (1024 * 1024)
    except Exception:
        pass
    return 0.0


class TestZeroRetention:
    """Test zero retention of uploaded and inferred data across canonical endpoints."""

    def test_upload_zero_retention(self):
        """10 CSVs + 1 XLSX + 1 TXT uploaded to /api/v1/upload.

        Asserts that DataFrame count growth is bounded (<= 2) and no module-level
        container accumulates cross-request state.
        """
        # Warm-up call to initialize one-time FastAPI/schema structures
        warmup_df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        warmup_csv = warmup_df.to_csv(index=False).encode("utf-8")
        client.post("/api/v1/upload", files={"file": ("warmup.csv", io.BytesIO(warmup_csv), "text/csv")})

        gc.collect()
        df_count_before = _count_live_dataframes()
        containers_before = _get_module_container_sizes()

        # 1. 10 distinct CSV uploads
        for i in range(10):
            df_i = pd.DataFrame({
                f"col_a_{i}": [10 * i + j for j in range(20)],
                f"col_b_{i}": [1.5 * i + j for j in range(20)],
                f"col_cat_{i}": [f"grp_{j % 3}" for j in range(20)],
            })
            csv_bytes = df_i.to_csv(index=False).encode("utf-8")
            res = client.post(
                "/api/v1/upload",
                files={"file": (f"dataset_{i}.csv", io.BytesIO(csv_bytes), "text/csv")},
            )
            assert res.status_code == 200, f"Upload {i} failed: {res.text}"
            data = res.json()
            assert "fileId" in data

        # 2. 1 XLSX upload
        xlsx_buf = io.BytesIO()
        with pd.ExcelWriter(xlsx_buf, engine="openpyxl") as writer:
            pd.DataFrame({"x": [10, 20, 30], "y": [1.1, 2.2, 3.3]}).to_excel(writer, index=False)
        xlsx_bytes = xlsx_buf.getvalue()
        res_xlsx = client.post(
            "/api/v1/upload",
            files={"file": ("test_sheet.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert res_xlsx.status_code == 200, f"XLSX upload failed: {res_xlsx.text}"

        # 3. 1 Document/text upload (covers document parser branch)
        txt_bytes = b"Foresight document parsing test text. No data should be retained."
        res_txt = client.post(
            "/api/v1/upload",
            files={"file": ("notes.txt", io.BytesIO(txt_bytes), "text/plain")},
        )
        assert res_txt.status_code == 200, f"TXT upload failed: {res_txt.text}"

        gc.collect()
        df_count_after = _count_live_dataframes()
        containers_after = _get_module_container_sizes()

        # Assert no module-level container grew
        for name, size_before in containers_before.items():
            size_after = containers_after.get(name, 0)
            assert size_after == size_before, (
                f"Container {name} grew from {size_before} to {size_after}"
            )

        # Assert live DataFrame count growth is <= 2
        df_growth = df_count_after - df_count_before
        assert df_growth <= 2, (
            f"Live DataFrame count grew by {df_growth} (before={df_count_before}, after={df_count_after}). "
            f"Expected <= 2."
        )

    def test_forecast_zero_retention(self):
        """10 distinct calls to /api/v1/forecast do not retain DataFrames or cross-request state."""
        rng = np.random.default_rng(42)
        gc.collect()
        df_count_before = _count_live_dataframes()

        for i in range(10):
            df_i = pd.DataFrame({
                "date": pd.date_range("2023-01-01", periods=60, freq="D").astype(str),
                "sales": 100 + i * 5 + rng.integers(0, 50, 60),
            })
            csv_bytes = df_i.to_csv(index=False).encode("utf-8")
            res = client.post(
                "/api/v1/forecast",
                files={"file": (f"forecast_{i}.csv", io.BytesIO(csv_bytes), "text/csv")},
                data={"use_llm": "false"},
            )
            assert res.status_code == 200

        gc.collect()
        df_count_after = _count_live_dataframes()
        df_growth = df_count_after - df_count_before
        assert df_growth <= 2, f"Live DataFrame growth on /forecast was {df_growth} (expected <= 2)"

    def test_hypotheses_zero_retention(self):
        """10 distinct calls to /api/v1/hypotheses do not retain DataFrames or cross-request state."""
        gc.collect()
        df_count_before = _count_live_dataframes()

        for i in range(10):
            df_i = pd.DataFrame({
                "sales": [100 + i + j for j in range(20)],
                "promo": ["A"] * 10 + ["B"] * 10,
            })
            csv_bytes = df_i.to_csv(index=False).encode("utf-8")
            res = client.post(
                "/api/v1/hypotheses",
                files={"file": (f"hypo_{i}.csv", io.BytesIO(csv_bytes), "text/csv")},
                data={"use_llm": "false"},
            )
            assert res.status_code == 200

        gc.collect()
        df_count_after = _count_live_dataframes()
        df_growth = df_count_after - df_count_before
        assert df_growth <= 2, f"Live DataFrame growth on /hypotheses was {df_growth} (expected <= 2)"

    def test_segmentation_zero_retention(self):
        """10 distinct calls to /api/v1/segmentation do not retain DataFrames or cross-request state."""
        rng = np.random.default_rng(42)
        gc.collect()
        df_count_before = _count_live_dataframes()

        for i in range(10):
            data = rng.standard_normal((100, 5)) + i
            df_i = pd.DataFrame(data, columns=[f"feat_{c}" for c in range(5)])
            csv_bytes = df_i.to_csv(index=False).encode("utf-8")
            res = client.post(
                "/api/v1/segmentation",
                files={"file": (f"seg_{i}.csv", io.BytesIO(csv_bytes), "text/csv")},
            )
            assert res.status_code == 200

        gc.collect()
        df_count_after = _count_live_dataframes()
        df_growth = df_count_after - df_count_before
        assert df_growth <= 2, f"Live DataFrame growth on /segmentation was {df_growth} (expected <= 2)"

    def test_document_paths_zero_retention(
        self,
        sample_pdf_bytes,
        sample_docx_bytes,
        sample_txt_bytes,
        sample_md_bytes,
    ):
        """Sequential uploads of PDF, DOCX, TXT, and MD documents do not leak DataFrames or process state."""
        gc.collect()
        df_count_before = _count_live_dataframes()
        containers_before = _get_module_container_sizes()

        doc_fixtures = [
            ("doc.pdf", sample_pdf_bytes, "application/pdf"),
            ("doc.docx", sample_docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ("notes.txt", sample_txt_bytes, "text/plain"),
            ("report.md", sample_md_bytes, "text/markdown"),
        ]

        # 5 cycles of 4 document formats (20 uploads total)
        for cycle in range(5):
            for fname, content, mime in doc_fixtures:
                res = client.post(
                    "/api/v1/upload",
                    files={"file": (f"{cycle}_{fname}", io.BytesIO(content), mime)},
                )
                assert res.status_code == 200, f"Document upload {cycle}_{fname} failed: {res.text}"
                data = res.json()
                assert data["detectedKind"] == "document"
                assert "fileId" in data

        gc.collect()
        df_count_after = _count_live_dataframes()
        containers_after = _get_module_container_sizes()

        # Assert no live DataFrames leaked from document parsing
        assert df_count_after - df_count_before <= 2
        for name, size_before in containers_before.items():
            assert containers_after.get(name, 0) == size_before

    def test_xlsx_30_uploads_rss_benchmark(self):
        """Benchmark 30 sequential in-memory uploads of ~5MB XLSX to verify bounded RSS and zero retention."""
        # Generate ~4MB realistic in-memory XLSX workbook (3,500 rows, 85 columns)
        rng = np.random.default_rng(123)
        df = pd.DataFrame(rng.standard_normal((3500, 85)))
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False)
        xlsx_bytes = buf.getvalue()
        del df, buf
        gc.collect()

        assert len(xlsx_bytes) >= 2.5 * 1024 * 1024, f"XLSX payload should be multi-megabyte, got {len(xlsx_bytes)} bytes"

        # Warm-up upload
        client.post(
            "/api/v1/upload",
            files={"file": ("warmup.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        gc.collect()

        rss_before = _get_rss_mb()
        df_count_before = _count_live_dataframes()

        # Run 30 sequential uploads of the multi-megabyte in-memory XLSX
        for i in range(30):
            res = client.post(
                "/api/v1/upload",
                files={"file": (f"bench_{i}.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
            assert res.status_code == 200, f"Upload {i} failed: {res.text}"

        gc.collect()
        rss_after = _get_rss_mb()
        df_count_after = _count_live_dataframes()

        # Verify DataFrames are dereferenced and garbage collected
        df_growth = df_count_after - df_count_before
        assert df_growth <= 2, f"Live DataFrame growth was {df_growth} (expected <= 2)"

        # If RSS measurement is active on Windows, assert bounded RSS delta (no monotonic accumulation)
        if rss_before > 0 and rss_after > 0:
            rss_delta = rss_after - rss_before
            assert rss_delta < 150.0, f"Excessive RSS growth: {rss_delta:.1f} MB (before={rss_before:.1f}, after={rss_after:.1f})"

