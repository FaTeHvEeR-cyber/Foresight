"""Shared feature pipeline (single source of truth for training AND inference).

Everything the per-request forecaster needs to turn an arbitrary uploaded table into a
clean, leakage-free time series lives here: date-format / frequency inference, ID and
target-component drops, low-cardinality categorical detection, retail transaction
aggregation, calendar + lag + rolling features, and leakage-free mean encoding.

Offline benchmark scripts (Rossmann, Credit Card Fraud) should import from this module too,
so there is zero training-serving skew.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- frequency configs


@dataclass(frozen=True)
class FreqConfig:
    label: str                 # "D" | "W" | "M" | "Q"
    period: str                # pandas Period alias
    lags: tuple[int, ...]
    windows: tuple[int, ...]
    season: int
    holdout: int               # periods held out for validation (upper bound)
    default_horizon: int
    max_horizon: int
    name: str


FREQ_CONFIGS: dict[str, FreqConfig] = {
    "D": FreqConfig("D", "D", (1, 7, 14, 21, 28), (7, 30), 7, 42, 14, 90, "daily"),
    "W": FreqConfig("W", "W", (1, 2, 4, 8, 52), (4, 12), 52, 8, 8, 26, "weekly"),
    "M": FreqConfig("M", "M", (1, 2, 3, 6, 12), (3, 6), 12, 12, 12, 24, "monthly"),
    "Q": FreqConfig("Q", "Q", (1, 2, 4), (2, 4), 4, 4, 4, 8, "quarterly"),
}

_ID_NAME_HINTS = {"id", "index", "instant", "idx", "rownum", "row", "no", "unnamed: 0", "unnamed:0"}
_MEAN_AGG_HINTS = ("temp", "rate", "ratio", "price", "pct", "percent", "avg", "average", "hum", "wind")
_TARGET_HINTS = ("sales", "revenue", "cnt", "count", "total", "amount", "passenger", "demand",
                 "quantity", "target", "value", "volume", "units")


class SeriesTooShort(Exception):
    """Raised when the series cannot support even the smallest lag set. Message is user-facing."""


class NoDateColumn(Exception):
    pass


# --------------------------------------------------------------------------- date handling

_ISO_RE = re.compile(r"^\s*\d{4}[-/]\d{1,2}([-/]\d{1,2})?")
_DMY_RE = re.compile(r"^\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})")


def infer_dayfirst(values: pd.Series) -> tuple[bool, str]:
    """Return (dayfirst, label). `values` should be the UNIQUE string values of the column."""
    s = values.dropna().astype(str)
    if s.empty:
        return False, "unknown"
    if s.str.match(_ISO_RE).mean() > 0.9:
        return False, "iso"
    parts = s.str.extract(_DMY_RE).dropna()
    if parts.empty:
        return False, "other"
    a = parts[0].astype(int)
    b = parts[1].astype(int)
    a_gt, b_gt = (a > 12).any(), (b > 12).any()
    if a_gt and not b_gt:
        return True, "day-first"
    if b_gt and not a_gt:
        return False, "month-first"
    if a_gt and b_gt:
        return False, "mixed"
    # Ambiguous (all components <= 12): pick the reading that keeps the ORIGINAL row order smoother.
    sample = s.iloc[:500]
    scores = {}
    for dayfirst in (True, False):
        parsed = pd.to_datetime(sample, format="mixed", dayfirst=dayfirst, errors="coerce")
        d = parsed.diff().dt.days.abs().dropna()
        scores[dayfirst] = float(d.median()) if len(d) else np.inf
    if scores[True] == scores[False]:
        return False, "assumed month-first"
    best = min(scores, key=scores.get)
    return best, "day-first (inferred from order)" if best else "month-first (inferred from order)"


def parse_dates(col: pd.Series) -> tuple[pd.Series, str]:
    """Parse a whole column by parsing its unique values once (fast on transaction logs)."""
    if pd.api.types.is_datetime64_any_dtype(col):
        return col, "datetime"
    uniq = pd.Series(col.dropna().unique())
    dayfirst, label = infer_dayfirst(uniq)
    parsed = pd.to_datetime(uniq, format="mixed", dayfirst=dayfirst, errors="coerce")
    mapping = pd.Series(parsed.values, index=uniq.values)
    return col.map(mapping), label


def find_date_column(df: pd.DataFrame, hint: str | None = None) -> str:
    if hint:
        if hint not in df.columns:
            raise NoDateColumn(f"Date column {hint!r} not found.")
        return hint
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            return c
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]) or pd.api.types.is_bool_dtype(df[c]):
            continue
        sample = df[c].dropna().astype(str).head(200)
        if sample.empty:
            continue
        looks = sample.str.match(_ISO_RE).mean() > 0.9 or sample.str.match(_DMY_RE).mean() > 0.9
        if looks:
            return c
    raise NoDateColumn("No date column detected. Pass `date_col` explicitly.")


def infer_frequency(dates: pd.DatetimeIndex) -> str | None:
    u = pd.DatetimeIndex(sorted(set(dates.normalize())))
    if len(u) < 3:
        return None
    med = float(pd.Series(u).diff().dt.days.dropna().median())
    if med <= 1.5:
        return "D"
    if 6 <= med <= 8:
        return "W"
    if 27 <= med <= 32:
        return "M"
    if 88 <= med <= 93:
        return "Q"
    return None


# --------------------------------------------------------------------------- column roles


def detect_id_columns(df: pd.DataFrame, protect: set[str] | None = None) -> list[str]:
    protect = protect or set()
    out = []
    for c in df.columns:
        if c in protect:
            continue
        name = str(c).strip().lower()
        if name in _ID_NAME_HINTS or name.startswith("unnamed"):
            out.append(c)
            continue
        s = df[c]
        if pd.api.types.is_integer_dtype(s) and len(s) > 20 and s.notna().all():
            v = s.to_numpy()
            if (np.diff(v) == 1).all() or (np.diff(v) == -1).all():
                out.append(c)
    return out


def detect_categorical_candidates(df: pd.DataFrame, exclude: set[str] | None = None,
                                  max_unique: int = 12) -> list[str]:
    """Low-cardinality int/bool/text columns that behave like categories (Channel, season, ...)."""
    exclude = exclude or set()
    out = []
    for c in df.columns:
        if c in exclude:
            continue
        s = df[c].dropna()
        if s.empty:
            continue
        nun = s.nunique()
        if not (2 <= nun <= max_unique):
            continue
        if pd.api.types.is_bool_dtype(s):
            out.append(c)
        elif pd.api.types.is_integer_dtype(s):
            out.append(c)
        elif pd.api.types.is_float_dtype(s):
            if (s % 1 == 0).all():
                out.append(c)
        elif not pd.api.types.is_datetime64_any_dtype(s):
            if nun <= 20:
                out.append(c)
    return out


def detect_target_components(df: pd.DataFrame, target: str, candidates: list[str],
                             max_cols: int = 25) -> dict[str, str]:
    """Find columns that leak the target: near-duplicates and exact pair-sums (cnt = casual + registered)."""
    y = df[target].to_numpy(dtype="float64")
    cols = [c for c in candidates if c != target][:max_cols]
    vals = {c: df[c].to_numpy(dtype="float64") for c in cols}
    leaks: dict[str, str] = {}
    ok = ~np.isnan(y)
    for c, v in vals.items():
        m = ok & ~np.isnan(v)
        if m.sum() > 5 and np.allclose(y[m], v[m]):
            leaks[c] = f"identical to target {target!r}"
        elif m.sum() > 5 and np.std(v[m]) > 0 and np.std(y[m]) > 0 \
                and abs(np.corrcoef(y[m], v[m])[0, 1]) > 0.9999:
            leaks[c] = f"near-duplicate of target {target!r} (|r|>0.9999)"
    keys = [c for c in cols if c not in leaks]
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            m = ok & ~np.isnan(vals[a]) & ~np.isnan(vals[b])
            if m.sum() > 5 and np.allclose(y[m], vals[a][m] + vals[b][m]):
                leaks[a] = f"{target!r} = {a!r} + {b!r} (target component)"
                leaks[b] = f"{target!r} = {a!r} + {b!r} (target component)"
    return leaks


def pick_target(df: pd.DataFrame, exclude: set[str]) -> str:
    nums = [c for c in df.columns
            if c not in exclude and pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    if not nums:
        raise ValueError("No numeric column available to forecast.")
    for hint in _TARGET_HINTS:
        for c in nums:
            if hint in str(c).lower():
                return c
    return nums[-1]


# --------------------------------------------------------------------------- retail transactions


def find_col(df: pd.DataFrame, *names: str) -> str | None:
    lower = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n in lower:
            return lower[n]
    return None


def is_retail_transactions(df: pd.DataFrame) -> bool:
    return all(find_col(df, n) for n in ("invoiceno", "quantity", "unitprice", "invoicedate"))


def prepare_retail_daily(df: pd.DataFrame) -> tuple[pd.DataFrame, dict, str, str]:
    """Transaction log -> daily net revenue. Returns (frame[date, net_revenue], data_quality, date_format, date_col)."""
    inv, qty, price, dcol = (find_col(df, "invoiceno"), find_col(df, "quantity"),
                             find_col(df, "unitprice"), find_col(df, "invoicedate"))
    sub = df[[inv, qty, price, dcol]].copy()
    sub.columns = ["inv", "qty", "price", "dt"]
    n0 = len(sub)
    is_cancel = sub["inv"].astype(str).str.startswith("C") & (sub["qty"] <= 0)
    dq = {"rows_in": int(n0), "cancellation_rows_dropped": int(is_cancel.sum()),
          "cancellation_invoices": int(sub.loc[is_cancel, "inv"].nunique())}
    sub = sub[~is_cancel]
    bad_price = ~(sub["price"] > 0)
    dq["zero_or_negative_price_rows_dropped"] = int(bad_price.sum())
    sub = sub[~bad_price]
    dq["negative_quantity_rows_kept_as_net_returns"] = int((sub["qty"] < 0).sum())
    dates, fmt = parse_dates(sub["dt"])
    sub = sub.assign(date=dates.dt.normalize()).dropna(subset=["date"])
    sub["rev"] = sub["qty"].astype("float64") * sub["price"].astype("float64")
    daily = sub.groupby("date", as_index=False)["rev"].sum().rename(columns={"rev": "net_revenue"})
    dq["rows_used"] = int(len(sub))
    return daily, dq, fmt, dcol


# --------------------------------------------------------------------------- series preparation


@dataclass
class PreparedSeries:
    y: pd.Series
    exog: pd.DataFrame
    cfg: FreqConfig
    date_col: str
    target: str
    date_format: str
    dropped: dict[str, str] = field(default_factory=dict)
    categorical_candidates: list[str] = field(default_factory=list)
    data_quality: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _agg_kind(target: str) -> str:
    t = target.lower()
    return "mean" if any(h in t for h in _MEAN_AGG_HINTS) else "sum"


def prepare_series(df: pd.DataFrame, target: str | None = None, date_col: str | None = None) -> PreparedSeries:
    notes: list[str] = []
    dq: dict = {}
    dropped: dict[str, str] = {}

    if is_retail_transactions(df) and not date_col and not target:
        daily, dq, fmt, dcol = prepare_retail_daily(df)
        notes.append("Transaction log detected: aggregated to daily net revenue "
                     "(cancellations and zero/negative-price rows excluded).")
        frame, date_name, tgt, agg, fill = daily, "date", "net_revenue", "sum", "zero"
        exog_cols: list[str] = []
        cat_cands: list[str] = []
        date_col_report = dcol
    else:
        dcol = find_date_column(df, date_col)
        ids = detect_id_columns(df, protect={dcol, target} if target else {dcol})
        for c in ids:
            dropped[c] = "ID / row counter"
        tgt = target or pick_target(df, exclude={dcol, *ids})
        if tgt not in df.columns:
            raise ValueError(f"Target column {tgt!r} not found.")
        num_cols = [c for c in df.columns if c not in {dcol, tgt, *ids}
                    and pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
        dropped.update(detect_target_components(df, tgt, num_cols))
        exog_cols = [c for c in num_cols if c not in dropped]
        cat_cands = detect_categorical_candidates(df, exclude={dcol, tgt, *ids})
        dates, fmt = parse_dates(df[dcol])
        frame = pd.concat([dates.rename("date"), df[[tgt, *exog_cols]]], axis=1).dropna(subset=["date", tgt])
        agg = _agg_kind(tgt)
        fill = "interpolate"
        date_name = "date"
        date_col_report = dcol
        if fmt not in ("iso", "datetime", "unknown"):
            notes.append(f"Date format inferred as {fmt}.")

    cfg_label = infer_frequency(pd.DatetimeIndex(frame[date_name]))
    if cfg_label is None:
        raise SeriesTooShort("Could not infer a regular frequency (daily/weekly/monthly/quarterly) "
                             "from the date column, or fewer than 3 distinct dates were found.")
    cfg = FREQ_CONFIGS[cfg_label]

    frame = frame.assign(_p=pd.DatetimeIndex(frame[date_name]).to_period(cfg.period))
    if int(frame["_p"].duplicated().sum()) > 0:
        notes.append(f"Multiple rows per period were aggregated to {cfg.name} values "
                     f"({agg} for the target, mean for other numeric columns).")
    aggmap = {tgt: agg, **{c: "mean" for c in exog_cols}}
    grouped = frame.groupby("_p").agg(aggmap)
    full = pd.period_range(grouped.index.min(), grouped.index.max(), freq=cfg.period)
    gaps = len(full) - len(grouped)
    grouped = grouped.reindex(full)
    if gaps:
        dq["gaps_filled"] = int(gaps)
        if fill == "zero":
            grouped[tgt] = grouped[tgt].fillna(0.0)
            notes.append(f"{gaps} non-trading periods filled with 0 revenue.")
        else:
            grouped = grouped.interpolate(limit_direction="both")
            notes.append(f"{gaps} missing periods filled by linear interpolation.")
    grouped.index = grouped.index.to_timestamp()
    y = grouped[tgt].astype("float64")
    exog = grouped[exog_cols].astype("float64") if exog_cols else pd.DataFrame(index=grouped.index)
    return PreparedSeries(y=y, exog=exog, cfg=cfg, date_col=date_col_report, target=tgt, date_format=fmt,
                          dropped=dropped, categorical_candidates=cat_cands, data_quality=dq, notes=notes)


# --------------------------------------------------------------------------- features


def select_lags(cfg: FreqConfig, n: int) -> tuple[list[int], list[int], int]:
    """Shrink lags/windows until the series can support them. Returns (lags, windows, holdout)."""
    lags = list(cfg.lags)
    while True:
        wins = [w for w in cfg.windows if w <= n // 4]
        head = max(max(lags), min(lags) + max(wins, default=0))
        holdout = min(cfg.holdout, max(3, n // 4))
        if n - head - holdout >= 20:
            return lags, wins, holdout
        if len(lags) == 1:
            raise SeriesTooShort(
                f"Only {n} {cfg.name} periods found; at least {head + holdout + 20} are needed "
                f"to train and validate a forecast. Upload a longer history.")
        lags.pop()  # drop the longest lag and retry


def _cyc(v: np.ndarray, period: float) -> tuple[np.ndarray, np.ndarray]:
    ang = 2 * np.pi * v / period
    return np.sin(ang), np.cos(ang)


def calendar_features(idx: pd.DatetimeIndex, cfg: FreqConfig) -> pd.DataFrame:
    """Built from a dict in one shot (per-column inserts dominated latency in the recursive forecast loop)."""
    month = idx.month.to_numpy()
    d: dict[str, np.ndarray] = {"month": month, "quarter": idx.quarter.to_numpy()}
    d["month_sin"], d["month_cos"] = _cyc(month - 1, 12)
    if cfg.label == "D":
        dow = idx.dayofweek.to_numpy()
        d["dow"] = dow
        d["dom"] = idx.day.to_numpy()
        d["weekofyear"] = idx.isocalendar().week.to_numpy().astype(int)
        d["is_weekend"] = (dow >= 5).astype(int)
        d["dow_sin"], d["dow_cos"] = _cyc(dow, 7)
    elif cfg.label == "W":
        d["weekofyear"] = idx.isocalendar().week.to_numpy().astype(int)
    return pd.DataFrame(d, index=idx)


def build_features(y: pd.Series, exog: pd.DataFrame, cfg: FreqConfig,
                   lags: list[int], windows: list[int]) -> pd.DataFrame:
    """Leakage-free features: every target-derived column is shifted by >= min(lags)."""
    cal = calendar_features(y.index, cfg)
    d: dict[str, pd.Series] = {f"lag_{l}": y.shift(l) for l in lags}
    base = y.shift(min(lags))
    for w in windows:
        r = base.rolling(w, min_periods=w)
        d[f"roll{w}_mean"], d[f"roll{w}_std"] = r.mean(), r.std()
        d[f"roll{w}_min"], d[f"roll{w}_max"] = r.min(), r.max()
    for c in exog.columns:
        d[f"x_{c}_lag1"] = exog[c].shift(1)
    return pd.concat([cal, pd.DataFrame(d, index=y.index)], axis=1) if d else cal


# --- leakage-free smoothed mean encoding (expanding, shifted) ----------------------------------


def expanding_mean_encode(y: np.ndarray, cat: np.ndarray, m: float = 10.0) -> np.ndarray:
    """Encode each row using ONLY earlier rows of the same category (smoothed toward the running global mean)."""
    n = len(y)
    out = np.empty(n)
    sums: dict = {}
    cnts: dict = {}
    run_sum = 0.0
    for i in range(n):
        gmean = run_sum / i if i else 0.0
        k = cat[i]
        out[i] = (sums.get(k, 0.0) + m * gmean) / (cnts.get(k, 0) + m)
        sums[k] = sums.get(k, 0.0) + y[i]
        cnts[k] = cnts.get(k, 0) + 1
        run_sum += y[i]
    return out


def fit_mean_lookup(y: np.ndarray, cat: np.ndarray, m: float = 10.0) -> tuple[dict, float]:
    g = float(np.mean(y))
    df = pd.DataFrame({"y": y, "c": cat}).groupby("c")["y"].agg(["sum", "count"])
    return {k: float((r["sum"] + m * g) / (r["count"] + m)) for k, r in df.iterrows()}, g


def encode_columns(cfg: FreqConfig) -> list[tuple[str, str]]:
    """(feature_name, source_calendar_column) pairs that get mean encoding."""
    return [("enc_dow", "dow"), ("enc_month", "month")] if cfg.label == "D" else [("enc_month", "month")]
