import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))

import time
import pandas as pd
from fastapi.testclient import TestClient
from main import app
from src.analytics import forecast_engine as fe

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

# Test different configurations with TestClient
configs = [
    ("n_est=100, nj=1 (current)", dict(n_estimators=100, max_depth=4, learning_rate=0.08, subsample=1.0, colsample_bytree=1.0, tree_method="hist", max_bin=64, n_jobs=1, random_state=42, verbosity=0)),
    ("n_est=35, nj=-1 (Worker claim)", dict(n_estimators=35, max_depth=4, learning_rate=0.08, subsample=0.9, colsample_bytree=0.9, tree_method="hist", max_bin=64, n_jobs=-1, random_state=42, verbosity=0)),
    ("n_est=35, nj=2", dict(n_estimators=35, max_depth=4, learning_rate=0.08, subsample=0.9, colsample_bytree=0.9, tree_method="hist", max_bin=64, n_jobs=2, random_state=42, verbosity=0)),
    ("n_est=30, nj=2", dict(n_estimators=30, max_depth=4, learning_rate=0.08, subsample=0.9, colsample_bytree=0.9, tree_method="hist", max_bin=64, n_jobs=2, random_state=42, verbosity=0)),
    ("n_est=25, nj=2", dict(n_estimators=25, max_depth=4, learning_rate=0.08, subsample=0.9, colsample_bytree=0.9, tree_method="hist", max_bin=64, n_jobs=2, random_state=42, verbosity=0)),
]

client = TestClient(app)

for label, cfg in configs:
    fe.XGB_PARAMS.clear()
    fe.XGB_PARAMS.update(cfg)
    
    # Warm up client
    client.post("/api/v1/forecast", files={"file": ("day.csv", raw)}, data={"target": "cnt", "horizon": 14, "use_llm": "false"})
    
    # Timed runs
    print(f"\n=== Configuration: {label} ===")
    for run in range(3):
        r = client.post("/api/v1/forecast", files={"file": ("day.csv", raw)}, data={"target": "cnt", "horizon": 14, "use_llm": "false"})
        j = r.json()
        tm = j.get("timing_ms", {})
        print(f"Run {run+1}: compute_total={tm.get('compute_total')}ms (feat={tm.get('features')}, fit={tm.get('validation_fit')}, refit_fc={tm.get('refit_and_forecast')}) within_budget={tm.get('within_budget')}")
