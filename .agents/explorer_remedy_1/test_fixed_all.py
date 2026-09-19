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

print("Running FULL backend test suite with FIXED XGB_PARAMS:", fe.XGB_PARAMS)
ret = pytest.main(["backend/tests/", "-q"])
print("Exit code:", ret)
