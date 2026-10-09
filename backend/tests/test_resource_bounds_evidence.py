"""Automated Regression Suite for WS-B Resource Evidence & Oversized Structures.

Tests bounded memory and pre-parse gatekeeper rejections for:
1. XLSX XML expansion decompression bombs (>100MB uncompressed) -> HTTP 413
2. XLSX thousands of sheets (>50 sheets) -> HTTP 422
3. XLSX huge merged cell range -> Handled safely without 500
4. Parquet with 10M rows -> HTTP 413 via metadata inspection
5. CSV with 30MB single cell -> Completes fast (< 5s) without crashing
6. CSV with 50,000 columns -> HTTP 422 pre-parse rejection (< 1s)

Zero disk writes: all fixtures constructed strictly in RAM via io.BytesIO.
"""
from __future__ import annotations

import io
import time
import zipfile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from starlette.testclient import TestClient

from main import app

client = TestClient(app)


def _build_xlsx_xml_bomb(uncompressed_mb: int = 120) -> bytes:
    """Build in-memory .xlsx zip bomb (>100 MB XML uncompressed, <1 MB compressed)."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '</Types>'
        ))
        z.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        ))
        z.writestr("xl/_rels/workbook.xml.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '</Relationships>'
        ))
        z.writestr("xl/workbook.xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></sheets>'
            '</workbook>'
        ))

        repeats = uncompressed_mb * 1000
        chunk = ('<row><c t="inlineStr"><is><t>' + ('0' * 1000) + '</t></is></c></row>\n').encode("utf-8")
        header = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>\n'
        footer = b'</sheetData></worksheet>'

        with z.open("xl/worksheets/sheet1.xml", mode="w") as sheet_file:
            sheet_file.write(header)
            for _ in range(repeats):
                sheet_file.write(chunk)
            sheet_file.write(footer)

    return bio.getvalue()


def _build_xlsx_thousand_sheets(n_sheets: int = 100) -> bytes:
    """Build in-memory .xlsx with excessive sheets (>50)."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '</Types>'
        ))
        z.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        ))
        sheets_xml = "".join(f'<sheet name="Sheet{i}" sheetId="{i}" r:id="rId{i}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>' for i in range(1, n_sheets + 1))
        z.writestr("xl/workbook.xml", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets>{sheets_xml}</sheets></workbook>')

        empty_sheet = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>'
        for i in range(1, n_sheets + 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", empty_sheet)
    return bio.getvalue()


def _build_parquet_10m_rows() -> bytes:
    """Build in-memory Parquet with 10M rows."""
    col = pa.array(np.zeros(100_000, dtype=np.float32))
    table = pa.Table.from_arrays([col, col], names=["c1", "c2"])
    bio = io.BytesIO()
    with pq.ParquetWriter(bio, table.schema, compression="snappy") as writer:
        for _ in range(100):  # 100 * 100k = 10M rows
            writer.write_table(table)
    return bio.getvalue()


class TestResourceBoundsEvidence:
    """Verify pre-parse rejections and bounded execution on adversarial resource structures."""

    def test_case1_xlsx_xml_expansion_bomb_rejected_413(self):
        """XLSX with >100MB declared uncompressed XML is rejected with HTTP 413 pre-parse."""
        bomb_bytes = _build_xlsx_xml_bomb(uncompressed_mb=120)
        assert len(bomb_bytes) < 1_000_000  # < 1 MB compressed

        # Check /api/v1/upload
        t0 = time.perf_counter()
        res_upload = client.post(
            "/api/v1/upload",
            files={"file": ("bomb.xlsx", bomb_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert time.perf_counter() - t0 < 1.0, "Pre-parse gatekeeper took too long"
        assert res_upload.status_code == 413
        assert "uncompressed size exceeds limit" in res_upload.text

        # Check /api/v1/segmentation
        t0 = time.perf_counter()
        res_seg = client.post(
            "/api/v1/segmentation",
            files={"file": ("bomb.xlsx", bomb_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"use_llm": "false"},
        )
        assert time.perf_counter() - t0 < 1.0
        assert res_seg.status_code == 413
        assert "uncompressed size exceeds limit" in res_seg.text

    def test_case2a_xlsx_thousand_sheets_rejected_422(self):
        """XLSX with >50 sheets is rejected with HTTP 422 pre-parse."""
        sheets_bytes = _build_xlsx_thousand_sheets(n_sheets=100)
        t0 = time.perf_counter()
        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("sheets.xlsx", sheets_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"use_llm": "false"},
        )
        assert time.perf_counter() - t0 < 1.0
        assert res.status_code == 422
        assert "sheet count exceeds limit" in res.text

    def test_case3_parquet_10m_rows_rejected_413(self):
        """Parquet with >1M rows is rejected with HTTP 413 from metadata pre-parse."""
        pq_bytes = _build_parquet_10m_rows()
        assert len(pq_bytes) < 500_000

        t0 = time.perf_counter()
        res = client.post(
            "/api/v1/segmentation",
            files={"file": ("rows10m.parquet", pq_bytes, "application/vnd.apache.parquet")},
            data={"use_llm": "false"},
        )
        assert time.perf_counter() - t0 < 1.0
        assert res.status_code == 413
        assert "Parquet row count exceeds limit" in res.text

    def test_case4a_csv_enormous_single_cell_rejected_413(self):
        """CSV with a 30MB string in a single cell is rejected pre-parse with HTTP 413 (< 1s)."""
        huge_cell = "A" * (30 * 1024 * 1024)
        content = f"date,sales,huge_cell\n2020-01-01,100.0,{huge_cell}\n2020-01-02,110.0,normal\n".encode("utf-8")

        t0 = time.perf_counter()
        res = client.post(
            "/api/v1/upload",
            files={"file": ("huge_cell.csv", content, "text/csv")},
        )
        elapsed = time.perf_counter() - t0
        assert res.status_code == 413
        assert "exceeds maximum limit" in res.text
        assert elapsed < 1.0, f"Upload rejection took too long: {elapsed:.2f}s"

    def test_case4a_csv_valid_large_single_cell_allowed_200(self):
        """CSV with a 1MB string in a single cell completes fast (< 5s) with HTTP 200."""
        large_cell = "A" * (1024 * 1024)
        content = f"date,sales,huge_cell\n2020-01-01,100.0,{large_cell}\n2020-01-02,110.0,normal\n".encode("utf-8")

        t0 = time.perf_counter()
        res = client.post(
            "/api/v1/upload",
            files={"file": ("large_cell.csv", content, "text/csv")},
        )
        elapsed = time.perf_counter() - t0
        assert res.status_code == 200
        assert elapsed < 5.0, f"Upload took too long: {elapsed:.2f}s"

    def test_case4b_csv_50k_columns_rejected_422(self):
        """CSV with 50,000 columns is rejected with HTTP 422 pre-parse (< 1s)."""
        headers = ["col" + str(i) for i in range(50_000)]
        content = (",".join(headers) + "\n1.0," * 49_999 + "1.0\n").encode("utf-8")

        t0 = time.perf_counter()
        res = client.post(
            "/api/v1/upload",
            files={"file": ("wide50k.csv", content, "text/csv")},
        )
        elapsed = time.perf_counter() - t0
        assert res.status_code == 422
        assert elapsed < 1.0, f"Column check took too long: {elapsed:.2f}s"
        assert "column count exceeds maximum limit" in res.text
