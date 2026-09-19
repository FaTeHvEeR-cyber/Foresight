import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))

import time
import numpy as np
import pandas as pd
from src.analytics import feature_pipeline as fp
from src.analytics import forecast_engine as fe
from src.analytics.forecast_engine import _fit, _add_encodings, regression_metrics

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

df_bike = pd.read_csv(_get_dataset_path("day.csv"))
prep = fp.prepare_series(df_bike, target="cnt")

def step_by_step():
    t_start = time.perf_counter()
    cfg, y_s = prep.cfg, prep.y
    n = len(y_s)
    lags, wins, holdout = fp.select_lags(cfg, n)
    h = 14
    nonneg = bool(y_s.min() >= 0)
    log_target = nonneg

    t0 = time.perf_counter()
    F_all = fp.build_features(y_s, prep.exog, cfg, lags, wins)
    t1 = time.perf_counter()
    
    y = y_s.to_numpy()
    valid = ~F_all.isna().any(axis=1).to_numpy()
    split = n - holdout
    train_mask = valid & (np.arange(n) < split)
    hold_mask = valid & (np.arange(n) >= split)

    t2 = time.perf_counter()
    F_enc, lookups = _add_encodings(F_all, y, train_mask, cfg)
    t3 = time.perf_counter()

    m_ridge = _fit("ridge", F_enc[train_mask], y[train_mask], log_target)
    t4 = time.perf_counter()
    m_xgb = _fit("xgboost", F_enc[train_mask], y[train_mask], log_target)
    t5 = time.perf_counter()

    X_hold = F_enc[hold_mask]
    preds = {
        "ridge": m_ridge.predict_arr(X_hold.to_numpy(dtype="float64"), nonneg),
        "xgboost": m_xgb.predict_arr(X_hold.to_numpy(dtype="float32"), nonneg),
    }
    y_hold = y[hold_mask]
    metrics = {nm: regression_metrics(y_hold, p) for nm, p in preds.items()}
    sel = min(("ridge", "xgboost"), key=lambda k: metrics[k]["rmse"])
    t6 = time.perf_counter()

    # Refit / model choice
    if sel == "ridge":
        full_mask = valid
        F_full, lookups = _add_encodings(F_all, y, full_mask, cfg)
        final = _fit(sel, F_full[full_mask], y[full_mask], log_target)
    else:
        final = m_xgb
    t7 = time.perf_counter()

    last_p = y_s.index.to_period(cfg.period)[-1]
    future_idx = pd.PeriodIndex([last_p + k for k in range(1, h + 1)]).to_timestamp()
    ext_x = (pd.concat([prep.exog, pd.DataFrame(np.nan, index=future_idx, columns=prep.exog.columns)])
             .ffill() if len(prep.exog.columns) else pd.DataFrame(index=future_idx))
    t8 = time.perf_counter()

    cal_future = fp.calendar_features(future_idx, cfg)
    min_lag = min(lags)
    y_vals = np.empty(n + h, dtype="float64")
    y_vals[:n] = y_s.to_numpy()

    feat_names = final.feature_names
    feat_idx_map = {fn: idx for idx, fn in enumerate(feat_names)}
    row_arr = np.zeros((1, len(feat_names)), dtype="float32" if sel == "xgboost" else "float64")

    cal_col_indices = [(col, feat_idx_map[col]) for col in cal_future.columns if col in feat_idx_map]
    cal_arr = cal_future[[col for col, _ in cal_col_indices]].to_numpy(dtype="float32" if sel == "xgboost" else "float64")

    lag_col_indices = [(l, feat_idx_map[f"lag_{l}"]) for l in lags if f"lag_{l}" in feat_idx_map]
    roll_col_indices = []
    for w in wins:
        for stat in ("mean", "std", "min", "max"):
            fn = f"roll{w}_{stat}"
            if fn in feat_idx_map:
                roll_col_indices.append((w, stat, feat_idx_map[fn]))
    exog_col_indices = [(c, feat_idx_map[f"x_{c}_lag1"]) for c in prep.exog.columns if f"x_{c}_lag1" in feat_idx_map]
    lookup_col_indices = [(feat, src, lk, g, feat_idx_map[feat]) for feat, (src, lk, g) in lookups.items() if feat in feat_idx_map]

    ext_x_dict = {c: ext_x[c].to_numpy() for c in ext_x.columns}
    cal_future_dict = {c: cal_future[c].to_numpy() for c in cal_future.columns}
    t9 = time.perf_counter()

    out = []
    for step in range(h):
        pos = n + step
        for cal_idx, (_, target_idx) in enumerate(cal_col_indices):
            row_arr[0, target_idx] = cal_arr[step, cal_idx]
        for l, target_idx in lag_col_indices:
            row_arr[0, target_idx] = y_vals[pos - l]
        for w, stat, target_idx in roll_col_indices:
            sl = y_vals[pos - min_lag - w + 1 : pos - min_lag + 1]
            if stat == "mean":
                val = float(np.mean(sl))
            elif stat == "std":
                val = float(np.std(sl, ddof=1))
            elif stat == "min":
                val = float(np.min(sl))
            else:
                val = float(np.max(sl))
            row_arr[0, target_idx] = val
        for c, target_idx in exog_col_indices:
            row_arr[0, target_idx] = ext_x_dict[c][pos - 1]
        for feat, src, lk, g, target_idx in lookup_col_indices:
            val_src = cal_future_dict[src][step] if src in cal_future_dict else (
                ext_x_dict[src][pos - 1] if src in ext_x_dict else 0
            )
            row_arr[0, target_idx] = lk.get(val_src, g)

        yhat = float(final.predict_arr(row_arr, nonneg)[0])
        y_vals[pos] = yhat
        out.append(yhat)
    t10 = time.perf_counter()

    print(f"Total compute: {(t10 - t_start)*1000:.2f}ms")
    print(f"  build_features:      {(t1 - t0)*1000:.2f}ms")
    print(f"  add_encodings:       {(t3 - t2)*1000:.2f}ms")
    print(f"  fit_ridge:           {(t4 - t3)*1000:.2f}ms")
    print(f"  fit_xgboost:         {(t5 - t4)*1000:.2f}ms")
    print(f"  eval_holdout:        {(t6 - t5)*1000:.2f}ms")
    print(f"  refit:               {(t7 - t6)*1000:.2f}ms")
    print(f"  future_exog_prep:    {(t8 - t7)*1000:.2f}ms")
    print(f"  setup_recursive_map: {(t9 - t8)*1000:.2f}ms")
    print(f"  recursive_loop:      {(t10 - t9)*1000:.2f}ms")

# Run 5 times
print("Warming up...")
step_by_step()
print("\n--- 5 Timed Runs ---")
for i in range(5):
    print(f"\nRun {i+1}:")
    step_by_step()
