import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))

from src.analytics import forecast_engine as fe

PARAMS_35 = dict(
    n_estimators=35,
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
fe.XGB_PARAMS.update(PARAMS_35)
fe._warmup()

import pytest

print("Running test_phase3a.py and test_phase3a_real_data.py with n_estimators=35, n_jobs=2...")
ret = pytest.main(["backend/tests/test_phase3a.py", "backend/tests/test_phase3a_real_data.py", "-v"])
print("Exit code:", ret)
