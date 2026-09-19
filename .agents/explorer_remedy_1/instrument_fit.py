import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))

import time
import gc
import numpy as np
import pandas as pd
from xgboost import XGBRegressor

X_np = np.random.randn(700, 15).astype("float32")
y_np = np.random.randn(700).astype("float32")
X_df = pd.DataFrame(X_np, columns=[f"f_{i}" for i in range(15)])

xgb_params = dict(
    n_estimators=30,
    max_depth=4,
    learning_rate=0.08,
    subsample=0.9,
    colsample_bytree=0.9,
    tree_method="hist",
    max_bin=64,
    n_jobs=2,
    random_state=42,
    verbosity=0
)

# Test 30 iterations of fitting, timing each phase
print("Testing 30 iterations of new XGBRegressor.fit()...")
times = []
for i in range(30):
    t0 = time.perf_counter()
    
    # 1. to_numpy
    t_a = time.perf_counter()
    arr = X_df.to_numpy(dtype="float32")
    t_b = time.perf_counter()
    
    # 2. log1p
    t_c = time.perf_counter()
    y_trans = np.log1p(np.clip(y_np, 0, None))
    t_d = time.perf_counter()
    
    # 3. XGBRegressor init
    t_e = time.perf_counter()
    est = XGBRegressor(**xgb_params)
    t_f = time.perf_counter()
    
    # 4. fit
    t_g = time.perf_counter()
    est.fit(arr, y_trans)
    t_h = time.perf_counter()
    
    # 5. get_booster
    t_i = time.perf_counter()
    booster = est.get_booster()
    t_j = time.perf_counter()
    
    total_ms = (t_j - t0) * 1000
    fit_ms = (t_h - t_g) * 1000
    init_ms = (t_f - t_e) * 1000
    times.append(total_ms)
    
    if total_ms > 100 or i < 5:
        print(f"Iter {i+1:2d}: total={total_ms:6.1f}ms | init={init_ms:4.1f}ms | fit={fit_ms:6.1f}ms")

print(f"\nSummary over 30 runs: min={min(times):.1f}ms, max={max(times):.1f}ms, mean={np.mean(times):.1f}ms, >100ms count={sum(1 for t in times if t > 100)}")
