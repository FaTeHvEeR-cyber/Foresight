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

import pytest

# Run pytest on the specific test with -vv -s --tb=short
pytest.main(["backend/tests/test_phase3a_real_data.py", "-k", "test_api_real_bike_forecast", "-vv", "-s", "--tb=long"])
