"""Re-benchmark harness for Phase 3B follow-up (WS-E).

Executes all 9 required benchmark cases in isolation:
- 10 measured runs per case (+ 1 warm-up run discarded)
- Records compute time (median & p95), total endpoint time (median & p95),
  response size, and peak RSS.
- Zero disk writes: all payloads generated in-memory via io.BytesIO.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import gc
import io
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import numpy as np
import pandas as pd
from starlette.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from main import app
from src.analytics.outlier_engine import aggregate_retail_rfm

client = TestClient(app)

# Memory tracking via Windows API
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

def get_peak_rss_mb() -> float:
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    if _get_mem_fn(_current_proc, ctypes.byref(pmc), pmc.cb):
        return pmc.PeakWorkingSetSize / (1024 * 1024)
    return 0.0

DATASET_CANDIDATES = [
    Path(r"C:\Users\rfate\Desktop\report\project\Project - 2\Datasets\phase-3A"),
    Path(r"C:\Users\rfate\Desktop\report\project\Project - 2\Datasets"),
    BACKEND_DIR / "data",
    BACKEND_DIR.parent / "data",
]

def find_dataset(*names: str) -> Path | None:
    for base in DATASET_CANDIDATES:
        for n in names:
            p = base / n
            if p.exists():
                return p
    return None

def make_synthetic_csv_bytes(n_rows: int, n_cols: int = 4, seed: int = 42) -> bytes:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(
        rng.normal(10.0, 5.0, (n_rows, n_cols)).astype(np.float32),
        columns=[f"col_{i}" for i in range(n_cols)],
    )
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()

def benchmark_payload(
    name: str,
    filename: str,
    payload_bytes: bytes,
    sla_description: str,
    runs: int = 10,
) -> Dict[str, Any]:
    print(f"\n---> Benchmarking {name} ({len(payload_bytes)/1024:.1f} KB payload)...")
    
    # 1. Warm-up run (discarded)
    r_warm = client.post(
        "/api/v1/segmentation",
        files={"file": (filename, payload_bytes, "text/csv")},
        data={"use_llm": "false"},
    )
    assert r_warm.status_code == 200, f"Warm-up failed: {r_warm.text[:200]}"
    del r_warm
    gc.collect()

    compute_times: List[float] = []
    endpoint_times: List[float] = []
    response_sizes: List[int] = []
    peak_rss_samples: List[float] = []
    budget_tiers: List[str] = []
    within_budgets: List[bool] = []

    for i in range(runs):
        t0 = time.perf_counter()
        r = client.post(
            "/api/v1/segmentation",
            files={"file": (filename, payload_bytes, "text/csv")},
            data={"use_llm": "false"},
        )
        total_time_ms = (time.perf_counter() - t0) * 1000
        assert r.status_code == 200, f"Run {i+1} failed: {r.text[:200]}"

        body = r.content
        res_json = r.json()
        tm = res_json.get("timing_ms", {})
        compute_ms = tm.get("compute_total", 0.0)

        compute_times.append(compute_ms)
        endpoint_times.append(total_time_ms)
        response_sizes.append(len(body))
        peak_rss_samples.append(get_peak_rss_mb())
        budget_tiers.append(tm.get("budget_tier", "unknown"))
        within_budgets.append(tm.get("within_budget", False))

        del r, body, res_json
        gc.collect()

    comp_med = float(np.median(compute_times))
    comp_p95 = float(np.percentile(compute_times, 95))
    endp_med = float(np.median(endpoint_times))
    endp_p95 = float(np.percentile(endpoint_times, 95))
    resp_size_kb = float(np.median(response_sizes)) / 1024
    peak_rss = float(max(peak_rss_samples))
    tier = budget_tiers[-1]

    print(f"     Compute: median={comp_med:.1f}ms, p95={comp_p95:.1f}ms | Endpoint: median={endp_med:.1f}ms, p95={endp_p95:.1f}ms | Tier: {tier} | Peak RSS: {peak_rss:.1f}MB")

    return {
        "case": name,
        "sla": sla_description,
        "compute_median_ms": round(comp_med, 1),
        "compute_p95_ms": round(comp_p95, 1),
        "endpoint_median_ms": round(endp_med, 1),
        "endpoint_p95_ms": round(endp_p95, 1),
        "response_size_kb": round(resp_size_kb, 1),
        "peak_rss_mb": round(peak_rss, 1),
        "tier": tier,
        "all_within_budget": all(within_budgets),
    }

def main():
    print("=" * 90)
    print("FORESIGHT PHASE 3B RE-BENCHMARK SUITE (10 RUNS, MEDIAN + P95, ISOLATED)")
    print("=" * 90)

    results: List[Dict[str, Any]] = []

    # 1. Synthetic 1k
    b_1k = make_synthetic_csv_bytes(1_000, 4)
    results.append(benchmark_payload("Synthetic 1k", "syn_1k.csv", b_1k, "strictly < 200 ms"))

    # 2. Synthetic 5k
    b_5k = make_synthetic_csv_bytes(5_000, 4)
    results.append(benchmark_payload("Synthetic 5k", "syn_5k.csv", b_5k, "strictly < 200 ms"))

    # 3. Synthetic 5,001
    b_5001 = make_synthetic_csv_bytes(5_001, 4)
    results.append(benchmark_payload("Synthetic 5,001", "syn_5001.csv", b_5001, "strictly < 500 ms"))

    # 4. Synthetic 10k
    b_10k = make_synthetic_csv_bytes(10_000, 4)
    results.append(benchmark_payload("Synthetic 10k", "syn_10k.csv", b_10k, "strictly < 500 ms"))

    # 5. Synthetic 20k
    b_20k = make_synthetic_csv_bytes(20_000, 4)
    results.append(benchmark_payload("Synthetic 20k", "syn_20k.csv", b_20k, "strictly < 500 ms"))

    # 6. Credit Card 20k subsample
    p_cc = find_dataset("creditcard.csv")
    if p_cc:
        df_cc_full = pd.read_csv(p_cc)
        rng = np.random.default_rng(42)
        sub_idx = rng.choice(len(df_cc_full), size=20_000, replace=False)
        df_cc_20k = df_cc_full.iloc[sub_idx].reset_index(drop=True)
        buf_cc = io.BytesIO()
        df_cc_20k.to_csv(buf_cc, index=False)
        b_cc_20k = buf_cc.getvalue()
        results.append(benchmark_payload("Credit Card 20k subsample", "creditcard_20k.csv", b_cc_20k, "strictly < 500 ms"))
        del df_cc_full, df_cc_20k, buf_cc, b_cc_20k
        gc.collect()
    else:
        print("[SKIP] creditcard.csv not found for 20k subsample benchmark.")

    # 7. Wholesale Customers (as is, 440 rows)
    p_w = find_dataset("Wholesale customers data.csv", "Wholesale_customers_data.csv")
    if p_w:
        b_w = p_w.read_bytes()
        results.append(benchmark_payload("Wholesale Customers", "wholesale.csv", b_w, "strictly < 200 ms"))
    else:
        print("[SKIP] Wholesale customers data.csv not found.")

    # 8. Online Retail (RFM) (as is, 4,338 customer rows)
    p_r = find_dataset("online_retail.csv")
    if p_r:
        df_raw_retail = pd.read_csv(p_r, encoding="latin-1")
        rfm_features, customer_context = aggregate_retail_rfm(df_raw_retail)
        # Prepare pure customer-level RFM CSV
        buf_rfm = io.BytesIO()
        customer_context.to_csv(buf_rfm, index=False)
        b_rfm = buf_rfm.getvalue()
        results.append(benchmark_payload("Online Retail (RFM customer table)", "online_retail_rfm.csv", b_rfm, "strictly < 200 ms"))
        del df_raw_retail, rfm_features, customer_context, buf_rfm, b_rfm
        gc.collect()
    else:
        print("[SKIP] online_retail.csv not found.")

    # 9. Synthetic 300k rows x 6 columns (measured, not gated)
    print("\nGenerating Synthetic 300,000 rows x 6 columns...")
    b_300k = make_synthetic_csv_bytes(300_000, 6)
    results.append(benchmark_payload("Synthetic 300k (6 cols)", "syn_300k.csv", b_300k, "measured, not gated"))
    del b_300k
    gc.collect()

    print("\n" + "=" * 115)
    print("FINAL BENCHMARK RESULTS TABLE")
    print("=" * 115)
    print(f"{'Case':<35} | {'SLA Target':<20} | {'Compute Med':<11} | {'Compute p95':<11} | {'Endpoint Med':<12} | {'Resp Size':<9} | {'Peak RSS':<8} | {'Tier'}")
    print("-" * 115)
    for r in results:
        print(f"{r['case']:<35} | {r['sla']:<20} | {r['compute_median_ms']:>8.1f} ms | {r['compute_p95_ms']:>8.1f} ms | {r['endpoint_median_ms']:>9.1f} ms | {r['response_size_kb']:>6.1f} KB | {r['peak_rss_mb']:>5.1f} MB | {r['tier']}")
    print("=" * 115)

if __name__ == "__main__":
    main()
