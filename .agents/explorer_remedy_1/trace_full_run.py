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
fe._warmup()

from fastapi.testclient import TestClient
old_post = TestClient.post

def new_post(self, *args, **kwargs):
    resp = old_post(self, *args, **kwargs)
    try:
        j = resp.json()
        if "timing_ms" in j and "/api/v1/forecast" in str(args[0]):
            print(f"\n>>> [FORECAST TIMING in test_api_real_bike_forecast]: {j['timing_ms']}")
    except Exception:
        pass
    return resp

TestClient.post = new_post

import pytest

# Run from test_phase2_exit_criteria through test_phase3a_real_data
pytest.main([
    "backend/tests/test_memory_lifecycle.py",
    "backend/tests/test_phase3a.py",
    "backend/tests/test_phase3a_real_data.py",
    "-s"
])
