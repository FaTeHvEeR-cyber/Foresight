import time
import numpy as np
from xgboost import XGBRegressor

X = np.random.randn(700, 15).astype("float32")
y = np.random.randn(700).astype("float32")

for n_jobs in [1, 2, 4, -1]:
    print(f"\n--- Testing n_jobs={n_jobs} ---")
    for i in range(5):
        t0 = time.perf_counter()
        est = XGBRegressor(
            n_estimators=30,
            max_depth=4,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            tree_method="hist",
            max_bin=64,
            n_jobs=n_jobs,
            random_state=42,
            verbosity=0
        )
        est.fit(X, y)
        t1 = time.perf_counter()
        print(f"Run {i+1}: {(t1 - t0)*1000:.1f}ms")
