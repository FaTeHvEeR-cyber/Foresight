import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))

import time
import pandas as pd
from fastapi.testclient import TestClient
from main import app

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

client = TestClient(app)

print("=== Sending Request 1 (warm-up) ===")
t0 = time.perf_counter()
r1 = client.post("/api/v1/forecast", files={"file": ("day.csv", raw)}, data={"target": "cnt", "horizon": 14, "use_llm": "false"})
t1 = time.perf_counter()
j1 = r1.json()
print("Req 1 total time:", (t1 - t0)*1000, "json timing:", j1.get("timing_ms"))

print("=== Sending Request 2 ===")
t0 = time.perf_counter()
r2 = client.post("/api/v1/forecast", files={"file": ("day.csv", raw)}, data={"target": "cnt", "horizon": 14, "use_llm": "false"})
t1 = time.perf_counter()
j2 = r2.json()
print("Req 2 total time:", (t1 - t0)*1000, "json timing:", j2.get("timing_ms"))
print("selected_model:", j2.get("selected_model"))
