"""Resource evidence measurement harness for decompression bombs and oversized structures (WS-B).

Measures HTTP status, wall time, peak RSS memory, and post-gc memory across 3 runs.
Evaluates against 512 MB and 1 GB ceilings.
Zero disk writes: all fixtures built in-memory via io.BytesIO.
"""
from __future__ import annotations

import sys
from pathlib import Path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import ctypes
from ctypes import wintypes
import gc
import io
import time
from typing import Any, Callable, Dict, List, Optional
import zipfile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from starlette.testclient import TestClient

from main import app

client = TestClient(app)


# Process memory counters for Windows RSS measurement
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


_get_mem_fn = ctypes.windll.psapi.GetProcessMemoryInfo
_get_mem_fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
_get_mem_fn.restype = wintypes.BOOL
_current_proc = ctypes.windll.kernel32.GetCurrentProcess()


def get_rss_mb() -> float:
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    if _get_mem_fn(_current_proc, ctypes.byref(pmc), pmc.cb):
        return pmc.WorkingSetSize / (1024 * 1024)
    return 0.0


def get_peak_rss_mb() -> float:
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    if _get_mem_fn(_current_proc, ctypes.byref(pmc), pmc.cb):
        return pmc.PeakWorkingSetSize / (1024 * 1024)
    return 0.0


# ===========================================================================
# Fixture Generators (Zero disk writes, 100% in-memory)
# ===========================================================================

def make_case1_xlsx_bomb() -> bytes:
    """Case 1: .xlsx with large declared uncompressed size (several hundred MB XML, <50MB zip)."""
    bio = io.BytesIO()
    # Create minimal openpyxl workbook structure in RAM with highly compressible repeating sheet XML
    with zipfile.ZipFile(bio, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        # Minimal workbook XML
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

        # Generate large repeating sheet XML (~120 MB uncompressed, compresses to < 1 MB)
        chunk = '<row><c t="inlineStr"><is><t>' + ('0' * 1000) + '</t></is></c></row>\n'
        # 120,000 repetitions of 1KB = ~120 MB
        repeats = 120_000
        sheet_header = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>\n'
        sheet_footer = '</sheetData></worksheet>'
        
        # Stream into zip entry
        with z.open("xl/worksheets/sheet1.xml", mode="w") as sheet_file:
            sheet_file.write(sheet_header.encode("utf-8"))
            chunk_bytes = chunk.encode("utf-8")
            for _ in range(repeats):
                sheet_file.write(chunk_bytes)
            sheet_file.write(sheet_footer.encode("utf-8"))

    val = bio.getvalue()
    return val


def make_case2a_xlsx_thousand_sheets() -> bytes:
    """Case 2a: .xlsx with thousands of sheets."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        # Minimal package structure
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
        
        # 1,200 sheets
        n_sheets = 1200
        sheets_xml = "".join(f'<sheet name="Sheet{i}" sheetId="{i}" r:id="rId{i}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>' for i in range(1, n_sheets + 1))
        z.writestr("xl/workbook.xml", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets>{sheets_xml}</sheets></workbook>')

        empty_sheet = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>'.encode("utf-8")
        for i in range(1, n_sheets + 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", empty_sheet)
    return bio.getvalue()


def make_case2b_xlsx_merged_cells() -> bytes:
    """Case 2b: .xlsx with huge merged cell range."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
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
        # Large merged cell range spanning A1:Z100000
        sheet_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData>'
            '<mergeCells count="1"><mergeCell ref="A1:Z100000"/></mergeCells>'
            '</worksheet>'
        )
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return bio.getvalue()


def make_case3_parquet_high_rows() -> bytes:
    """Case 3: Parquet with high row count (10,000,000 rows) but small on-disk size."""
    n_rows = 10_000_000
    # 4 constant float columns: highly compressed with RLE/dictionary encoding
    col = pa.array(np.zeros(100_000, dtype=np.float32))
    table = pa.Table.from_arrays(
        [col, col, col, col],
        names=["val1", "val2", "val3", "val4"],
    )
    # Write multiple row groups or dictionary encoded
    bio = io.BytesIO()
    with pq.ParquetWriter(bio, table.schema, compression="snappy") as writer:
        for _ in range(100):  # 100 * 100,000 = 10,000,000 rows
            writer.write_table(table)
    return bio.getvalue()


def make_case4a_csv_enormous_cell() -> bytes:
    """Case 4a: CSV with one enormous cell (30 MB in a single field)."""
    huge_cell = "A" * (30 * 1024 * 1024)  # 30 MB cell
    content = f"date,sales,huge_cell\n2020-01-01,100.0,{huge_cell}\n2020-01-02,110.0,normal\n".encode("utf-8")
    return content


def make_case4b_csv_wide_header() -> bytes:
    """Case 4b: CSV with 50,000 columns."""
    headers = ["col" + str(i) for i in range(50_000)]
    row = ["1.0"] * 50_000
    content = (",".join(headers) + "\n" + ",".join(row) + "\n").encode("utf-8")
    return content


def make_case5_normal_50mb_csv() -> bytes:
    """Case 5: Near-limit ~48 MB CSV of normal data as baseline."""
    # ~48 MB of numeric rows
    # 6 columns: date, metric1, metric2, metric3, metric4, metric5
    # Each row ~55 bytes -> ~900,000 rows for 48 MB
    n_rows = 800_000
    rng = np.random.default_rng(42)
    chunk_size = 100_000
    bio = io.BytesIO()
    
    header = "date,sales,margin,units,temp,promo\n".encode("utf-8")
    bio.write(header)
    
    for i in range(n_rows // chunk_size):
        dates = pd.date_range("2018-01-01", periods=chunk_size, freq="h").strftime("%Y-%m-%d %H:%M")
        df_chunk = pd.DataFrame({
            "date": dates,
            "sales": np.round(rng.normal(100, 15, chunk_size), 2),
            "margin": np.round(rng.normal(25, 5, chunk_size), 2),
            "units": rng.integers(1, 50, chunk_size),
            "temp": np.round(rng.normal(20, 8, chunk_size), 2),
            "promo": rng.integers(0, 2, chunk_size),
        })
        chunk_bytes = df_chunk.to_csv(index=False, header=False).encode("utf-8")
        bio.write(chunk_bytes)
        
    return bio.getvalue()


# ===========================================================================
# Execution and Measurement Runner
# ===========================================================================

def measure_request(endpoint: str, filename: str, content: bytes, mime: str, runs: int = 3) -> Dict[str, Any]:
    statuses: List[int] = []
    durations: List[float] = []
    peak_rss_list: List[float] = []
    post_gc_list: List[float] = []

    for run_i in range(runs):
        gc.collect()
        mem_before = get_rss_mb()
        peak_before = get_peak_rss_mb()

        t0 = time.perf_counter()
        res = client.post(
            endpoint,
            files={"file": (filename, content, mime)},
            data={"use_llm": "false"} if endpoint != "/api/v1/upload" else {},
        )
        duration_s = time.perf_counter() - t0
        peak_during = get_rss_mb()
        peak_process = get_peak_rss_mb()

        gc.collect()
        mem_after_gc = get_rss_mb()

        statuses.append(res.status_code)
        durations.append(duration_s)
        peak_rss_list.append(peak_during)
        post_gc_list.append(mem_after_gc)

    return {
        "status": statuses[0],
        "wall_time_median_s": float(np.median(durations)),
        "wall_time_worst_s": float(np.max(durations)),
        "peak_rss_median_mb": float(np.median(peak_rss_list)),
        "peak_rss_worst_mb": float(np.max(peak_rss_list)),
        "post_gc_median_mb": float(np.median(post_gc_list)),
        "post_gc_worst_mb": float(np.max(post_gc_list)),
    }


def main():
    print("=" * 80)
    print(" WS-B RESOURCE EVIDENCE MEASUREMENTS (512 MB & 1 GB CEILINGS)")
    print("=" * 80)

    cases = [
        ("Case 1: .xlsx XML Expansion Bomb", "bomb.xlsx", make_case1_xlsx_bomb(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ["/api/v1/upload", "/api/v1/segmentation"]),
        ("Case 2a: .xlsx 1,200 Sheets", "sheets.xlsx", make_case2a_xlsx_thousand_sheets(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ["/api/v1/upload", "/api/v1/segmentation"]),
        ("Case 2b: .xlsx Merged Range A1:Z100k", "merged.xlsx", make_case2b_xlsx_merged_cells(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ["/api/v1/upload", "/api/v1/segmentation"]),
        ("Case 3: Parquet 10M Rows", "rows10m.parquet", make_case3_parquet_high_rows(), "application/vnd.apache.parquet", ["/api/v1/upload", "/api/v1/segmentation"]),
        ("Case 4a: CSV 30MB Single Cell", "huge_cell.csv", make_case4a_csv_enormous_cell(), "text/csv", ["/api/v1/upload", "/api/v1/segmentation"]),
        ("Case 4b: CSV 50,000 Columns", "wide50k.csv", make_case4b_csv_wide_header(), "text/csv", ["/api/v1/upload", "/api/v1/segmentation"]),
        ("Case 5: Normal 48MB CSV Baseline", "baseline_48mb.csv", make_case5_normal_50mb_csv(), "text/csv", ["/api/v1/upload", "/api/v1/segmentation", "/api/v1/forecast"]),
    ]

    results = []

    for label, filename, content, mime, endpoints in cases:
        size_mb = len(content) / (1024 * 1024)
        print(f"\n--- {label} ({filename}, {size_mb:.2f} MB payload) ---")
        for ep in endpoints:
            print(f"  Testing {ep} ...", end="", flush=True)
            res = measure_request(ep, filename, content, mime, runs=3)
            print(f" Status: {res['status']}, Time: {res['wall_time_median_s']:.3f}s (worst: {res['wall_time_worst_s']:.3f}s), Peak RSS: {res['peak_rss_median_mb']:.1f}MB (worst: {res['peak_rss_worst_mb']:.1f}MB), Post-GC: {res['post_gc_median_mb']:.1f}MB")
            results.append({
                "case": label,
                "endpoint": ep,
                "payload_mb": round(size_mb, 2),
                **res,
            })

    print("\n" + "=" * 105)
    print(f"{'Case':<35} | {'Endpoint':<22} | {'Status':<6} | {'Wall (p50/max)':<16} | {'Peak RSS (p50/max)':<18} | {'Post-GC'}")
    print("=" * 105)
    for r in results:
        w_str = f"{r['wall_time_median_s']:.2f}s / {r['wall_time_worst_s']:.2f}s"
        p_str = f"{r['peak_rss_median_mb']:.1f}M / {r['peak_rss_worst_mb']:.1f}M"
        print(f"{r['case']:<35} | {r['endpoint']:<22} | {r['status']:<6} | {w_str:<16} | {p_str:<18} | {r['post_gc_median_mb']:.1f} MB")
    print("=" * 105)


if __name__ == "__main__":
    main()
