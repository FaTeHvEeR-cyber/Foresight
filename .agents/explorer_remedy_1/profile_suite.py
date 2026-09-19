import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))

import time
import pandas as pd
from src.analytics import feature_pipeline as fp
from src.analytics import forecast_engine as fe
from src.analytics.forecast_engine import run_forecast
from src.analytics.hypothesis_engine import run_hypotheses
from src.analytics.loader import load_tabular
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

print("Current fe.XGB_PARAMS:", fe.XGB_PARAMS)

# 1. Airline
print("\n--- Test 1: Airline Passengers ---")
df_air = pd.read_csv(_get_dataset_path("airline-passengers.csv"))
prep_air = fp.prepare_series(df_air)
run_forecast(prep_air)
res_air = run_forecast(prep_air, horizon=12)
print("Airline timing:", res_air["timing_ms"])

# 2. Bike validation
print("\n--- Test 2: Bike Sharing Validation ---")
df_bike = pd.read_csv(_get_dataset_path("day.csv"))
prep_bike = fp.prepare_series(df_bike, target="cnt")
run_forecast(prep_bike)
res_bike = run_forecast(prep_bike, horizon=14)
print("Bike timing:", res_bike["timing_ms"])

# 3. Wholesale
print("\n--- Test 3: Wholesale ---")
df_ws = pd.read_csv(_get_dataset_path("Wholesale customers data.csv"))
res_ws = run_hypotheses(df_ws, target="Fresh")
print("Wholesale timing:", res_ws["timing_ms"])

# 4. Retail
print("\n--- Test 4: Online Retail ---")
raw_ret = _get_dataset_path("online_retail.csv").read_bytes()
df_ret = load_tabular(raw_ret, "online_retail.csv")
prep_ret = fp.prepare_series(df_ret)
res_ret = run_forecast(prep_ret, horizon=14)
print("Retail timing:", res_ret["timing_ms"])
del df_ret, raw_ret, prep_ret, res_ret
import gc; gc.collect()

# 5. Rossmann
print("\n--- Test 5: Rossmann Promo Lift ---")
bp = Path("backend/data/benchmark_data.parquet")
if bp.exists():
    df_bm = pd.read_parquet(bp)
    res_bm = run_hypotheses(df_bm, target="units_sold", group_cols=["promo_flag"])
    print("Rossmann timing:", res_bm["timing_ms"])

# 6. API Bike Forecast
print("\n--- Test 6: API Bike Forecast ---")
client = TestClient(app)
raw_bike = _get_dataset_path("day.csv").read_bytes()
client.post("/api/v1/forecast", files={"file": ("day.csv", raw_bike)}, data={"target": "cnt", "horizon": 14, "use_llm": "false"})
r = client.post("/api/v1/forecast", files={"file": ("day.csv", raw_bike)}, data={"target": "cnt", "horizon": 14, "use_llm": "false"})
j = r.json()
print("API Bike Forecast response timing:", j.get("timing_ms"))
print("within_budget:", j.get("timing_ms", {}).get("within_budget"))
