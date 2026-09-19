"""Engine A: per-request in-memory forecasting (Ridge + fast-fit XGBoost). No artifacts, no disk."""
from __future__ import annotations

import gc
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from . import feature_pipeline as fp

XGB_PARAMS = dict(
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


def _warmup() -> None:
    """One-time warm-up so the first inference request does not suffer DLL/OpenMP initialization lag."""
    try:
        rng = np.random.RandomState(42)
        X = rng.randn(100, 15).astype("float32")
        y = rng.randn(100).astype("float32")
        est = XGBRegressor(**XGB_PARAMS)
        est.fit(X, y)
        est.get_booster().inplace_predict(X[:1])
        pipe = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
        pipe.fit(X.astype("float64"), y.astype("float64"))
    except Exception:
        pass


_warmup()


# --------------------------------------------------------------------------- metrics


def regression_metrics(y: np.ndarray, yhat: np.ndarray) -> dict:
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    err = y - yhat
    nz = y != 0
    rmspe = float(np.sqrt(np.mean((err[nz] / y[nz]) ** 2))) if nz.any() else None
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = float(1 - np.sum(err ** 2) / ss_tot) if ss_tot > 0 else None
    return {"rmspe": rmspe, "mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err ** 2))),
            "r2": r2, "n": len(y), "n_zero_actuals_excluded_from_rmspe": int((~nz).sum())}


# --------------------------------------------------------------------------- model wrapper


@dataclass
class _Model:
    name: str
    est: Any
    log_target: bool
    feature_names: list[str]
    linear_weights: np.ndarray | None = None
    linear_bias: float | None = None
    booster: Any | None = None

    def predict(self, X: pd.DataFrame, nonneg: bool) -> np.ndarray:
        if self.name == "ridge" and self.linear_weights is not None:
            arr = X[self.feature_names].to_numpy(dtype="float64")
            p = arr @ self.linear_weights + self.linear_bias
        else:
            p = self.est.predict(X[self.feature_names].to_numpy(dtype="float32" if self.name == "xgboost" else "float64"))
        if self.log_target:
            p = np.expm1(p)
        return np.clip(p, 0, None) if nonneg else p


    def predict_arr(self, arr: np.ndarray, nonneg: bool) -> np.ndarray:
        if self.name == "ridge" and self.linear_weights is not None:
            p = arr.astype("float64", copy=False) @ self.linear_weights + self.linear_bias
        elif self.name == "xgboost":
            b = self.booster if self.booster is not None else self.est.get_booster()
            p = b.inplace_predict(arr.astype("float32", copy=False))
        else:
            p = self.est.predict(arr)
        if self.log_target:
            p = np.expm1(p)
        return np.clip(p, 0, None) if nonneg else p


def _fit(name: str, X: pd.DataFrame, y: np.ndarray, log_target: bool) -> _Model:
    cols = list(X.columns)
    if name == "ridge":
        est = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
        est.fit(X.to_numpy(dtype="float64"), y)
        scaler = est.named_steps["standardscaler"]
        ridge = est.named_steps["ridge"]
        effective_coef = ridge.coef_ / scaler.scale_
        effective_intercept = float(ridge.intercept_ - np.sum(scaler.mean_ * effective_coef))
        return _Model("ridge", est, False, cols, effective_coef, effective_intercept)
    est = XGBRegressor(**XGB_PARAMS)
    est.fit(X.to_numpy(dtype="float32"), np.log1p(y) if log_target else y)
    return _Model("xgboost", est, log_target, cols, booster=est.get_booster())


def _add_encodings(F: pd.DataFrame, y: np.ndarray, train_mask: np.ndarray, cfg: fp.FreqConfig):
    """Expanding (leakage-free) encodings for train rows; train-fold lookup for later rows."""
    F = F.copy()
    lookups = {}
    for feat, src in fp.encode_columns(cfg):
        cat = F[src].to_numpy()
        col = np.full(len(F), np.nan)
        ti = np.flatnonzero(train_mask)
        col[ti] = fp.expanding_mean_encode(y[ti], cat[ti])
        lk, g = fp.fit_mean_lookup(y[ti], cat[ti])
        lookups[feat] = (src, lk, g)
        rest = ~train_mask
        col[rest] = [lk.get(c, g) for c in cat[rest]]
        F[feat] = col
    return F, lookups


# --------------------------------------------------------------------------- main entry


def run_forecast(prep: fp.PreparedSeries, horizon: int | None = None) -> dict:
    t0 = time.perf_counter()
    cfg, y_s = prep.cfg, prep.y
    n = len(y_s)
    lags, wins, holdout = fp.select_lags(cfg, n)          # may raise SeriesTooShort
    h = min(max(horizon or cfg.default_horizon, 1), cfg.max_horizon)
    nonneg = bool(y_s.min() >= 0)
    log_target = nonneg

    F_all = fp.build_features(y_s, prep.exog, cfg, lags, wins)
    y = y_s.to_numpy()
    valid = ~F_all.isna().any(axis=1).to_numpy()
    idx_valid = np.flatnonzero(valid)
    split = n - holdout
    train_mask = valid & (np.arange(n) < split)
    hold_mask = valid & (np.arange(n) >= split)

    F_enc, lookups = _add_encodings(F_all, y, train_mask, cfg)
    t_prep = time.perf_counter()

    models = {nm: _fit(nm, F_enc[train_mask], y[train_mask], log_target) for nm in ("ridge", "xgboost")}
    X_hold = F_enc[hold_mask]
    preds = {
        "ridge": models["ridge"].predict_arr(X_hold.to_numpy(dtype="float64"), nonneg),
        "xgboost": models["xgboost"].predict_arr(X_hold.to_numpy(dtype="float32"), nonneg),
    }
    y_hold = y[hold_mask]
    metrics = {nm: regression_metrics(y_hold, p) for nm, p in preds.items()}

    naive_shift = cfg.season if n > cfg.season + holdout + 5 else 1
    naive = y_s.shift(naive_shift).to_numpy()[hold_mask]
    if not np.isnan(naive).any():
        metrics["seasonal_naive"] = regression_metrics(y_hold, naive)
    sel = min(("ridge", "xgboost"), key=lambda k: metrics[k]["rmse"])
    if "seasonal_naive" in metrics and metrics["seasonal_naive"]["rmse"] > 0:
        skill = 1 - metrics[sel]["rmse"] / metrics["seasonal_naive"]["rmse"]
    else:
        skill = None
    t_train = time.perf_counter()

    # Fast refit for Ridge (1-2ms); reuse validated XGBoost model (avoids redundant 100-tree refit).
    if sel == "ridge":
        final = _fit(sel, F_enc[valid], y[valid], log_target)
    else:
        final = models[sel]

    last_p = y_s.index[-1].to_period(cfg.period)
    future_idx = pd.PeriodIndex([last_p + k for k in range(1, h + 1)]).to_timestamp()
    ext_x = (pd.concat([prep.exog, pd.DataFrame(np.nan, index=future_idx, columns=prep.exog.columns)])
             .ffill().bfill().fillna(0.0) if len(prep.exog.columns) else pd.DataFrame(index=future_idx))

    cal_future = fp.calendar_features(future_idx, cfg)
    min_lag = min(lags)
    y_vals = np.empty(n + h, dtype="float64")
    y_vals[:n] = y_s.to_numpy()

    # Precompute column indices in final.feature_names for blazing fast numpy updates
    feat_names = final.feature_names
    feat_idx_map = {fn: idx for idx, fn in enumerate(feat_names)}
    row_arr = np.zeros((1, len(feat_names)), dtype="float32" if sel == "xgboost" else "float64")

    # Map static calendar features
    cal_col_indices = [(col, feat_idx_map[col]) for col in cal_future.columns if col in feat_idx_map]
    cal_arr = cal_future[[col for col, _ in cal_col_indices]].to_numpy(dtype="float32" if sel == "xgboost" else "float64")

    # Map dynamic lag, rolling, exog, lookup indices
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

    out = []
    for step in range(h):
        pos = n + step
        # Fill calendar features
        for cal_idx, (_, target_idx) in enumerate(cal_col_indices):
            row_arr[0, target_idx] = cal_arr[step, cal_idx]
        # Fill lags
        for l, target_idx in lag_col_indices:
            row_arr[0, target_idx] = y_vals[pos - l]
        # Fill rolling stats
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
        # Fill exog
        for c, target_idx in exog_col_indices:
            row_arr[0, target_idx] = ext_x_dict[c][pos - 1]
        # Fill lookups
        for feat, src, lk, g, target_idx in lookup_col_indices:
            val_src = cal_future_dict[src][step] if src in cal_future_dict else (
                ext_x_dict[src][pos - 1] if src in ext_x_dict else 0
            )
            row_arr[0, target_idx] = lk.get(val_src, g)

        yhat = float(final.predict_arr(row_arr, nonneg)[0])
        y_vals[pos] = yhat
        out.append(yhat)
    fc = np.asarray(out)
    band = 1.96 * metrics[sel]["rmse"]
    lower = fc - band
    upper = fc + band
    if nonneg:
        lower = np.clip(lower, 0, None)

    tail = min(n, 365)
    hold_idx = y_s.index[hold_mask]
    result = {
        "status": "ok",
        "dataset": {"date_column": prep.date_col, "target": prep.target, "frequency": cfg.name,
                    "date_format": prep.date_format, "n_periods": n,
                    "start": y_s.index[0].date().isoformat(), "end": y_s.index[-1].date().isoformat()},
        "series": {"dates": [d.date().isoformat() for d in y_s.index[-tail:]],
                   "actuals": [round(float(v), 4) for v in y_s.iloc[-tail:]]},
        "holdout": {"dates": [d.date().isoformat() for d in hold_idx],
                    "actuals": [round(float(v), 4) for v in y_hold],
                    "predictions": {k: [round(float(v), 4) for v in p] for k, p in preds.items()}},
        "forecast": {"model": sel, "horizon": h,
                     "dates": [d.date().isoformat() for d in future_idx],
                     "values": [round(float(v), 4) for v in fc],
                     "lower": [round(float(v), 4) for v in lower],
                     "upper": [round(float(v), 4) for v in upper],
                     "interval_note": "Approximate 95% band (±1.96 × holdout RMSE), constant width."},
        "metrics": metrics,
        "selected_model": sel,
        "skill_vs_seasonal_naive": None if skill is None else round(float(skill), 4),
        "features": {"lags": lags, "rolling_windows": wins, "holdout_periods": holdout,
                     "n_features": F_all.shape[1] + len(lookups),
                     "exogenous_columns_lagged_1": list(prep.exog.columns)},
        "preprocessing": {"dropped_columns": [{"name": k, "reason": v} for k, v in prep.dropped.items()],
                          "categorical_candidates": prep.categorical_candidates,
                          "data_quality": prep.data_quality, "notes": prep.notes},
        "timing_ms": {"features": round((t_prep - t0) * 1000, 1),
                      "validation_fit": round((t_train - t_prep) * 1000, 1),
                      "refit_and_forecast": round((time.perf_counter() - t_train) * 1000, 1),
                      "compute_total": round((time.perf_counter() - t0) * 1000, 1)},
    }
    del F_all, F_enc, models
    gc.collect()
    return result
