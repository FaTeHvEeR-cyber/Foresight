"""Measurement harness for XLSX expansion and memory evidence (WS-C).

Measures HTTP status, parse wall time, baseline RSS, peak RSS, RSS delta, and post-GC RSS
across 3 runs for realistic XLSX workbooks at ~5 MB, ~12 MB, ~25 MB, and ~50 MB compressed.
Evaluates POST /api/v1/upload and POST /api/v1/segmentation.

Zero disk writes: 100% in-memory via io.BytesIO.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import gc
import io
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
import zipfile

import numpy as np
import pandas as pd
from starlette.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from config.settings import settings
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


def build_realistic_xlsx(num_rows: int, num_sheets: int = 1) -> Tuple[bytes, float, float, float]:
    """Generate realistic in-memory .xlsx file with mixed numeric, date, and repeated strings."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        types_xml = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
            '<Default Extension="xml" ContentType="application/xml"/>',
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        ]
        for s in range(1, num_sheets + 1):
            types_xml.append(f'<Override PartName="/xl/worksheets/sheet{s}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        types_xml.append('</Types>')
        z.writestr("[Content_Types].xml", "".join(types_xml))

        z.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>',
        )

        wb_rels = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
        ]
        for s in range(1, num_sheets + 1):
            wb_rels.append(f'<Relationship Id="rId{s}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{s}.xml"/>')
        wb_rels.append('</Relationships>')
        z.writestr("xl/_rels/workbook.xml.rels", "".join(wb_rels))

        wb_sheets = "".join(
            f'<sheet name="Sheet{s}" sheetId="{s}" r:id="rId{s}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
            for s in range(1, num_sheets + 1)
        )
        z.writestr(
            "xl/workbook.xml",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets>{wb_sheets}</sheets></workbook>',
        )

        rows_per_sheet = num_rows // num_sheets
        header_xml = (
            b'<row r="1">'
            b'<c r="A1" t="inlineStr"><is><t>order_id</t></is></c>'
            b'<c r="B1" t="inlineStr"><is><t>date</t></is></c>'
            b'<c r="C1" t="inlineStr"><is><t>customer_type</t></is></c>'
            b'<c r="D1" t="inlineStr"><is><t>region</t></is></c>'
            b'<c r="E1" t="inlineStr"><is><t>category</t></is></c>'
            b'<c r="F1" t="inlineStr"><is><t>sales</t></is></c>'
            b'<c r="G1" t="inlineStr"><is><t>quantity</t></is></c>'
            b'<c r="H1" t="inlineStr"><is><t>discount</t></is></c>'
            b'<c r="I1" t="inlineStr"><is><t>profit</t></is></c>'
            b'</row>\n'
        )

        regions = ["North America", "Europe", "Asia Pacific", "Latin America", "Middle East"]
        cats = ["Consumer Technology", "Office Essentials", "Ergonomic Furniture", "Industrial Supplies"]
        custs = ["Enterprise Consumer", "Global Corporate", "Regional Small Business", "Direct Partner"]

        block_size = 5000
        rng = np.random.default_rng(123)
        sales_arr = rng.uniform(10.0, 5000.0, block_size)
        qty_arr = rng.integers(1, 100, block_size)
        disc_arr = rng.uniform(0.0, 0.4, block_size)
        prof_arr = rng.normal(120.0, 60.0, block_size)
        dates = [f"202{(i % 4)}-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}" for i in range(block_size)]

        lines = []
        for i in range(block_size):
            r = regions[i % len(regions)]
            c = cats[i % len(cats)]
            cu = custs[i % len(custs)]
            d = dates[i]
            s_val = sales_arr[i]
            q_val = qty_arr[i]
            di_val = disc_arr[i]
            pr_val = prof_arr[i]
            row_str = (
                f'<row>'
                f'<c><v>{i}</v></c>'
                f'<c t="inlineStr"><is><t>{d}</t></is></c>'
                f'<c t="inlineStr"><is><t>{cu}</t></is></c>'
                f'<c t="inlineStr"><is><t>{r}</t></is></c>'
                f'<c t="inlineStr"><is><t>{c}</t></is></c>'
                f'<c><v>{s_val:.2f}</v></c>'
                f'<c><v>{q_val}</v></c>'
                f'<c><v>{di_val:.2f}</v></c>'
                f'<c><v>{pr_val:.2f}</v></c>'
                f'</row>\n'
            )
            lines.append(row_str.encode("utf-8"))
        big_block = b"".join(lines)

        for s in range(1, num_sheets + 1):
            ws_header = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>\n'
            ws_footer = b'</sheetData></worksheet>'
            with z.open(f"xl/worksheets/sheet{s}.xml", mode="w") as sf:
                sf.write(ws_header)
                sf.write(header_xml)
                reps = rows_per_sheet // block_size
                for _ in range(max(1, reps)):
                    sf.write(big_block)
                sf.write(ws_footer)

    content = bio.getvalue()
    comp_mb = len(content) / (1024 * 1024)
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        uncomp_mb = sum(info.file_size for info in z.infolist()) / (1024 * 1024)
    ratio = uncomp_mb / comp_mb
    return content, comp_mb, uncomp_mb, ratio


def measure_endpoint_runs(
    endpoint: str,
    content: bytes,
    filename: str = "test.xlsx",
    runs: int = 3,
) -> Dict[str, Any]:
    """Run endpoint 3 times, measuring wall time, baseline RSS, peak RSS, delta, and post-GC RSS."""
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    durations: List[float] = []
    base_rss_list: List[float] = []
    peak_rss_list: List[float] = []
    delta_rss_list: List[float] = []
    post_gc_list: List[float] = []
    statuses: List[int] = []

    for _ in range(runs):
        gc.collect()
        time.sleep(0.05)
        idle_rss = get_rss_mb()

        t0 = time.perf_counter()
        res = client.post(
            endpoint,
            files={"file": (filename, content, mime)},
            data={"use_llm": "false"} if endpoint != "/api/v1/upload" else {},
        )
        elapsed = time.perf_counter() - t0
        peak_rss = get_rss_mb()
        delta_rss = max(0.0, peak_rss - idle_rss)

        gc.collect()
        time.sleep(0.05)
        after_gc = get_rss_mb()

        statuses.append(res.status_code)
        durations.append(elapsed)
        base_rss_list.append(idle_rss)
        peak_rss_list.append(peak_rss)
        delta_rss_list.append(delta_rss)
        post_gc_list.append(after_gc)

    return {
        "status": statuses[0],
        "time_med_s": float(np.median(durations)),
        "time_max_s": float(np.max(durations)),
        "base_rss_med_mb": float(np.median(base_rss_list)),
        "base_rss_max_mb": float(np.max(base_rss_list)),
        "peak_rss_med_mb": float(np.median(peak_rss_list)),
        "peak_rss_max_mb": float(np.max(peak_rss_list)),
        "delta_rss_med_mb": float(np.median(delta_rss_list)),
        "delta_rss_max_mb": float(np.max(delta_rss_list)),
        "post_gc_med_mb": float(np.median(post_gc_list)),
        "post_gc_max_mb": float(np.max(post_gc_list)),
    }


def main():
    print("=" * 110)
    print(" WS-C: XLSX EXPANSION & MEMORY MEASUREMENT HARNESS")
    print(f" Current settings.MAX_XLSX_UNCOMPRESSED_BYTES: {settings.MAX_XLSX_UNCOMPRESSED_BYTES / (1024 * 1024):.0f} MB")
    print("=" * 110)

    # 1. Generate fixtures
    # Target: ~5 MB, ~12 MB, ~25 MB, ~50 MB compressed
    configs = [
        ("~5 MB XLSX (1 sheet)", 240_000, 1),
        ("~12 MB XLSX (2 sheets)", 570_000, 2),
        ("~25 MB XLSX (2 sheets)", 1_180_000, 2),
        ("~50 MB XLSX (3 sheets)", 2_360_000, 3),
    ]

    fixtures = []
    for label, rows, sheets in configs:
        print(f"Generating {label} ({rows:,} rows)... ", end="", flush=True)
        t0 = time.perf_counter()
        content, comp_mb, uncomp_mb, ratio = build_realistic_xlsx(rows, sheets)
        t_gen = time.perf_counter() - t0
        print(f"Done in {t_gen:.2f}s | Comp: {comp_mb:.2f} MB, Uncomp: {uncomp_mb:.2f} MB, Ratio: {ratio:.2f}x")
        fixtures.append({
            "label": label,
            "rows": rows,
            "sheets": sheets,
            "content": content,
            "comp_mb": comp_mb,
            "uncomp_mb": uncomp_mb,
            "ratio": ratio,
        })

    # 2. Run measurements across endpoints
    endpoints = ["/api/v1/upload", "/api/v1/segmentation"]
    results = []

    for f in fixtures:
        print(f"\n--- Testing {f['label']} (Comp: {f['comp_mb']:.2f} MB, Uncomp: {f['uncomp_mb']:.2f} MB, Ratio: {f['ratio']:.2f}x) ---")
        for ep in endpoints:
            print(f"  Running 3x on {ep} ... ", end="", flush=True)
            m = measure_endpoint_runs(ep, f["content"], filename=f"test_{f['sheets']}sh.xlsx", runs=3)
            print(f"Status: {m['status']}, Time: {m['time_med_s']:.3f}s / {m['time_max_s']:.3f}s, Peak: {m['peak_rss_med_mb']:.1f}MB, Delta: +{m['delta_rss_med_mb']:.1f}MB")
            results.append({
                "label": f["label"],
                "comp_mb": f["comp_mb"],
                "uncomp_mb": f["uncomp_mb"],
                "ratio": f["ratio"],
                "endpoint": ep,
                **m,
            })

    # 3. Print markdown table
    print("\n" + "=" * 115)
    print(" FINAL WS-C MEASUREMENT TABLE (3 Runs Each: Median / Worst)")
    print("=" * 115)
    header = (
        f"| Payload | Endpoint | Comp (MB) | Uncomp (MB) | Ratio | HTTP Status "
        f"| Parse Time (Med/Worst) | Peak RSS (Med/Worst) | RSS Delta (Med/Worst) | Post-GC RSS | Current Cap Verdict |"
    )
    print(header)
    print("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")

    for r in results:
        cap_verdict = "PASS (Accepted)" if r["status"] == 200 else f"REJECTED (HTTP {r['status']})"
        t_str = f"{r['time_med_s']:.3f}s / {r['time_max_s']:.3f}s"
        p_str = f"{r['peak_rss_med_mb']:.1f} MB / {r['peak_rss_max_mb']:.1f} MB"
        d_str = f"+{r['delta_rss_med_mb']:.1f} MB / +{r['delta_rss_max_mb']:.1f} MB"
        g_str = f"{r['post_gc_med_mb']:.1f} MB"
        print(
            f"| **{r['label']}** | `{r['endpoint']}` | {r['comp_mb']:.2f} MB | {r['uncomp_mb']:.2f} MB | {r['ratio']:.2f}x "
            f"| **{r['status']}** | {t_str} | {p_str} | {d_str} | {g_str} | **{cap_verdict}** |"
        )
    print("=" * 115)


if __name__ == "__main__":
    main()
