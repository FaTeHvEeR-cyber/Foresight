import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))

from src.analytics import forecast_engine as fe
FIXED_PARAMS = dict(
    n_estimators=30,
    max_depth=4,
    learning_rate=0.08,
    subsample=0.9,
    colsample_bytree=0.9,
    tree_method="hist",
    max_bin=64,
    n_jobs=2,
    random_state=42,
    verbosity=0,
)
fe.XGB_PARAMS.clear()
fe.XGB_PARAMS.update(FIXED_PARAMS)

import pandas as pd
from src.analytics import feature_pipeline as fp
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

# 1. Airline
df_air = pd.read_csv(_get_dataset_path("airline-passengers.csv"))
prep_air = fp.prepare_series(df_air)
run_forecast(prep_air)
res_air = run_forecast(prep_air, horizon=12)

# 2. Bike validation
df_bike = pd.read_csv(_get_dataset_path("day.csv"))
prep_bike = fp.prepare_series(df_bike, target="cnt")
run_forecast(prep_bike)
res_bike = run_forecast(prep_bike, horizon=14)

# 3. Wholesale
df_ws = pd.read_csv(_get_dataset_path("Wholesale customers data.csv"))
res_ws = run_hypotheses(df_ws, target="Fresh")

# 4. Retail
raw_ret = _get_dataset_path("online_retail.csv").read_bytes()
df_ret = load_tabular(raw_ret, "online_retail.csv")
prep_ret = fp.prepare_series(df_ret)
res_ret = run_forecast(prep_ret, horizon=14)
del df_ret, raw_ret, prep_ret, res_ret
import gc; gc.collect()

# 5. Rossmann
bp = Path("backend/data/benchmark_data.parquet")
if bp.exists():
    df_bm = pd.read_parquet(bp)
    res_bm = run_hypotheses(df_bm, target="units_sold", group_cols=["promo_flag"])

# 6. NOW EXACT test_api_real_bike_forecast
client = TestClient(app)
path = _get_dataset_path("day.csv")
raw = path.read_bytes()

# Warm-up request
print("Sending warm-up request...")
r_w = client.post(
    "/api/v1/forecast",
    files={"file": ("day.csv", raw)},
    data={"target": "cnt", "horizon": 14, "use_llm": "false"},
)
print("Warm-up response timing:", r_w.json().get("timing_ms"))

print("Sending second request...")
r = client.post(
    "/api/v1/forecast",
    files={"file": ("day.csv", raw)},
    data={"target": "cnt", "horizon": 14, "use_llm": "false"},
)
j = r.json()
print("Second response timing:", j.get("timing_ms"))
print("within_budget:", j.get("timing_ms", {}).get("within_budget"))
