import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))

import time
import concurrent.futures
import pandas as pd
from src.analytics import feature_pipeline as fp
from src.analytics import forecast_engine as fe
from src.api.analytics_router import _forecast_job

DATASET_CANDIDATES = [
    Path(r"C:\Users\rfate\Desktop\report\project\Project - 2\Datasets\phase-3A"),
    Path("backend/data"),
    Path("data"),
]

def _get_dataset_path(filename: str) -> Path:
    for base in DATASET_CANDIDATES:
        p = base / filename
        if p.exists():
            return p
    raise FileNotFoundError(filename)

day_path = _get_dataset_path("day.csv")
raw = day_path.read_bytes()

print("--- Direct execution on Main Thread ---")
_forecast_job(raw, "day.csv", "cnt", None, 14)
for i in range(3):
    res, _ = _forecast_job(raw, "day.csv", "cnt", None, 14)
    print(f"Main thread {i+1}:", res["timing_ms"])

print("\n--- Execution in ThreadPoolExecutor ---")
with concurrent.futures.ThreadPoolExecutor() as executor:
    fut = executor.submit(_forecast_job, raw, "day.csv", "cnt", None, 14)
    fut.result()
    for i in range(3):
        fut = executor.submit(_forecast_job, raw, "day.csv", "cnt", None, 14)
        res, _ = fut.result()
        print(f"ThreadPool {i+1}:", res["timing_ms"])
