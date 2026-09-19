"""Diagnostic script to profile forecast latency on bike sharing dataset."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from src.analytics import feature_pipeline as fp
from src.analytics.forecast_engine import run_forecast

d = pd.date_range("2018-01-01", "2019-12-31", freq="D")
t = np.arange(len(d))
rng = np.random.default_rng(0)
reg = 2000 + 3 * t + 500 * np.sin(2 * np.pi * t / 365) + 300 * (d.dayofweek < 5) + rng.normal(0, 120, len(d))
cas = 500 + 200 * np.sin(2 * np.pi * t / 365) + 250 * (d.dayofweek >= 5) + rng.normal(0, 60, len(d))
bdf = pd.DataFrame({
    "instant": t + 1,
    "dteday": d.strftime("%d-%m-%Y"),
    "season": (d.month % 12) // 3 + 1,
    "yr": (d.year - 2018),
    "mnth": d.month,
    "holiday": (np.arange(len(d)) % 50 == 0).astype(int),
    "weekday": d.dayofweek,
    "temp": 0.5 + 0.3 * np.sin(2 * np.pi * t / 365),
    "casual": cas.round(),
    "registered": reg.round(),
    "cnt": (cas.round() + reg.round()),
})

prep = fp.prepare_series(bdf, target="cnt")
print("Warm-up run...")
run_forecast(prep)

timings = []
for i in range(10):
    res = run_forecast(prep, horizon=14)
    tm = res["timing_ms"]
    timings.append(tm["compute_total"])
    print(f"Run {i+1:2d}: compute_total={tm['compute_total']:6.1f}ms (features={tm['features']:4.1f}ms, validation_fit={tm['validation_fit']:6.1f}ms, refit_forecast={tm['refit_and_forecast']:4.1f}ms)")

print(f"\nMean: {np.mean(timings):.1f}ms, Median: {np.median(timings):.1f}ms, Min: {np.min(timings):.1f}ms, Max: {np.max(timings):.1f}ms, P90: {np.percentile(timings, 90):.1f}ms")
print(f"Runs > 200ms budget: {sum(1 for t in timings if t > 200)} / 10")
