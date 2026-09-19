import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))

import pandas as pd
import numpy as np
from src.analytics import feature_pipeline as fp
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

# 1. Synthetic bike data from test_phase3a.py fixture
def make_synthetic_bike():
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", periods=730, freq="D")
    t = np.arange(len(dates))
    trend = 0.05 * t
    season_year = 10 * np.sin(2 * np.pi * t / 365.25)
    season_week = 5 * np.sin(2 * np.pi * t / 7)
    noise = np.random.normal(0, 2, len(dates))
    cnt = 100 + trend + season_year + season_week + noise
    return pd.DataFrame({
        "dteday": dates.strftime("%d-%m-%Y"),
        "instant": range(1, len(dates) + 1),
        "cnt": cnt,
        "casual": cnt * 0.3,
        "registered": cnt * 0.7,
        "temp": np.random.uniform(10, 30, len(dates)),
    })

synthetic_df = make_synthetic_bike()
prep_synth = fp.prepare_series(synthetic_df, target="cnt")

real_bike_df = pd.read_csv(_get_dataset_path("day.csv"))
prep_real_bike = fp.prepare_series(real_bike_df, target="cnt")

airline_df = pd.read_csv(_get_dataset_path("airline-passengers.csv"))
prep_airline = fp.prepare_series(airline_df)

for n_est in [25, 30, 35]:
    for nj in [2, -1]:
        params = dict(
            n_estimators=n_est,
            max_depth=4,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            tree_method="hist",
            max_bin=64,
            n_jobs=nj,
            random_state=42,
            verbosity=0,
        )
        fe.XGB_PARAMS.clear()
        fe.XGB_PARAMS.update(params)
        
        # 1. Synthetic
        fe.run_forecast(prep_synth)
        res_s = fe.run_forecast(prep_synth, horizon=14)
        
        # 2. Real bike
        fe.run_forecast(prep_real_bike)
        res_b = fe.run_forecast(prep_real_bike, horizon=14)
        
        # 3. Airline
        fe.run_forecast(prep_airline)
        res_a = fe.run_forecast(prep_airline, horizon=12)
        
        print(f"\n==========================================")
        print(f"n_estimators={n_est}, n_jobs={nj}")
        print(f"  Synthetic Bike (N=730):")
        print(f"    compute_total: {res_s['timing_ms']['compute_total']}ms")
        print(f"    Ridge R2: {res_s['metrics']['ridge']['r2']:.4f} | XGB R2: {res_s['metrics']['xgboost']['r2']:.4f} | Selected: {res_s['selected_model']}")
        print(f"  Real Bike (N=730):")
        print(f"    compute_total: {res_b['timing_ms']['compute_total']}ms")
        print(f"    Ridge R2: {res_b['metrics']['ridge']['r2']:.4f}, RMSE: {res_b['metrics']['ridge']['rmse']:.1f}")
        print(f"    XGB   R2: {res_b['metrics']['xgboost']['r2']:.4f}, RMSE: {res_b['metrics']['xgboost']['rmse']:.1f}")
        print(f"    Selected: {res_b['selected_model']} (XGB beats Ridge: {res_b['metrics']['xgboost']['rmse'] < res_b['metrics']['ridge']['rmse']})")
        print(f"  Real Airline (N=144):")
        print(f"    compute_total: {res_a['timing_ms']['compute_total']}ms")
        print(f"    Ridge R2: {res_a['metrics']['ridge']['r2']:.4f} | XGB R2: {res_a['metrics']['xgboost']['r2']:.4f} | Selected: {res_a['selected_model']}")
