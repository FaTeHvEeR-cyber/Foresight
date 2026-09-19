import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))

import time
import pandas as pd
from src.analytics import feature_pipeline as fp
from src.analytics import forecast_engine as fe
from src.api.analytics_router import _forecast_job
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
print("Using day_path:", day_path)
raw = day_path.read_bytes()
df = pd.read_csv(day_path)
prep = fp.prepare_series(df, target="cnt")

print("\n=== DIRECT fe.run_forecast with current settings ===")
print("fe.XGB_PARAMS:", fe.XGB_PARAMS)
fe.run_forecast(prep) # warm-up
for i in range(3):
    res = fe.run_forecast(prep, horizon=14)
    print(f"Run {i+1}:", res["timing_ms"], "Selected:", res["selected_model"], "XGB R2:", round(res["metrics"]["xgboost"]["r2"], 4), "Ridge R2:", round(res["metrics"]["ridge"]["r2"], 4))

print("\n=== VIA API _forecast_job ===")
for i in range(3):
    res, _ = _forecast_job(raw, "day.csv", "cnt", None, 14)
    print(f"Job {i+1}:", res["timing_ms"])

print("\n=== VIA TESTCLIENT ===")
client = TestClient(app)
client.post("/api/v1/forecast", files={"file": ("day.csv", raw)}, data={"target": "cnt", "horizon": 14, "use_llm": "false"})
for i in range(3):
    r = client.post("/api/v1/forecast", files={"file": ("day.csv", raw)}, data={"target": "cnt", "horizon": 14, "use_llm": "false"})
    j = r.json()
    print(f"Client {i+1}:", j["timing_ms"], "within_budget:", j["timing_ms"].get("within_budget"))
