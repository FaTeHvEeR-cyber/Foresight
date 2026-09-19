"""Statistical hypothesis tests: Welch's t-test (2 groups) and one-way ANOVA (3+ groups)."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
from scipy import stats

from . import feature_pipeline as fp

_NP_SAMPLE = 50_000
ALPHA = 0.05


def _holm(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = np.argsort(pvals)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvals[i]))
        adj[i] = running
    return adj.tolist()


def _label(v) -> str:
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))
    return str(v)


def run_hypotheses(df: pd.DataFrame, target: str | None = None, group_cols: list[str] | None = None,
                   max_tests: int = 8, seed: int = 42) -> dict:
    t0 = time.perf_counter()
    notes: list[str] = []
    skipped: list[dict] = []

    ids = fp.detect_id_columns(df, protect={target} if target else None)
    dates = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    cats = fp.detect_categorical_candidates(df, exclude={*ids, *dates, *([target] if target else [])})
    if target is None:
        nums = [c for c in df.columns if c not in {*ids, *dates, *cats}
                and pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
        if not nums:
            return {"status": "insufficient_data", "message": "No numeric column available to test.",
                    "tests": [], "skipped": [], "notes": []}
        target = next((c for h in fp._TARGET_HINTS for c in nums if h in str(c).lower()), nums[0])
        notes.append(f"Target not specified; using {target!r}.")
    elif target not in df.columns:
        raise ValueError(f"Target column {target!r} not found.")

    groups = [g for g in (group_cols or cats) if g in df.columns and g != target]
    if group_cols:
        missing = [g for g in group_cols if g not in df.columns]
        skipped += [{"column": g, "reason": "column not found"} for g in missing]
    y_all = pd.to_numeric(df[target], errors="coerce")
    rng = np.random.default_rng(seed)
    raw_tests = []
    for g in groups:
        sub = pd.DataFrame({"y": y_all, "g": df[g]}).dropna()
        counts = sub["g"].value_counts()
        keep = counts[counts >= 5].index
        sub = sub[sub["g"].isin(keep)]
        levels = sorted(sub["g"].unique().tolist(), key=lambda v: (str(type(v)), v))
        if len(levels) < 2:
            skipped.append({"column": g, "reason": "fewer than 2 groups with at least 5 rows"})
            continue
        arrays = [sub.loc[sub["g"] == lv, "y"].to_numpy(dtype="float64") for lv in levels]
        if all(np.var(a) == 0 for a in arrays):
            skipped.append({"column": g, "reason": "no variance in the target within groups"})
            continue
        gstats = [{"group": _label(lv), "n": int(len(a)), "mean": round(float(a.mean()), 4),
                   "std": round(float(a.std(ddof=1)), 4)} for lv, a in zip(levels, arrays)]
        skew = float(stats.skew(sub["y"].to_numpy()))
        # non-parametric cross-check on a capped, seeded sample
        samp = [a if len(a) <= _NP_SAMPLE else rng.choice(a, _NP_SAMPLE, replace=False) for a in arrays]
        if len(levels) == 2:
            a, b = arrays
            res = stats.ttest_ind(a, b, equal_var=False)
            pooled = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
            base = float(a.mean())
            entry = {"test": "welch_t", "statistic": float(res.statistic), "p_value": float(res.pvalue),
                     "df": float(res.df), "baseline_group": _label(levels[0]), "comparison_group": _label(levels[1]),
                     "mean_difference": float(b.mean() - a.mean()),
                     "lift_pct": None if base == 0 else round((float(b.mean()) / base - 1) * 100, 2),
                     "effect_size": {"name": "cohens_d", "value": None if pooled == 0 else float((b.mean() - a.mean()) / pooled)},
                     "nonparametric_p": float(stats.mannwhitneyu(samp[0], samp[1]).pvalue)}
        else:
            res = stats.f_oneway(*arrays)
            allv = np.concatenate(arrays)
            ssb = sum(len(a) * (a.mean() - allv.mean()) ** 2 for a in arrays)
            sst = float(((allv - allv.mean()) ** 2).sum())
            entry = {"test": "anova", "statistic": float(res.statistic), "p_value": float(res.pvalue),
                     "df": [len(arrays) - 1, int(len(allv) - len(arrays))],
                     "effect_size": {"name": "eta_squared", "value": None if sst == 0 else float(ssb / sst)},
                     "nonparametric_p": float(stats.kruskal(*samp).pvalue)}
        if not np.isfinite(entry["p_value"]):
            skipped.append({"column": g, "reason": "test undefined (degenerate variance)"})
            continue
        entry.update({"grouping_column": g, "target": target, "n_groups": len(levels),
                      "group_stats": gstats, "target_skew": round(skew, 2),
                      "skew_warning": abs(skew) > 2})
        raw_tests.append(entry)

    if len(raw_tests) > max_tests:
        raw_tests.sort(key=lambda e: e["p_value"])
        skipped += [{"column": e["grouping_column"], "reason": f"beyond top {max_tests} tests"} for e in raw_tests[max_tests:]]
        raw_tests = raw_tests[:max_tests]
    adj = _holm([e["p_value"] for e in raw_tests]) if raw_tests else []
    for e, pa in zip(raw_tests, adj):
        e["p_value_adjusted"] = pa
        e["significant"] = bool(pa < ALPHA)
        e["significant_unadjusted"] = bool(e["p_value"] < ALPHA)
        e["robust"] = bool((e["nonparametric_p"] < ALPHA) == e["significant_unadjusted"])
    raw_tests.sort(key=lambda e: e["p_value"])
    if any(e["skew_warning"] for e in raw_tests):
        notes.append("Target is heavily skewed; compare each test with its non-parametric p-value (Mann-Whitney / Kruskal-Wallis).")
    if len(raw_tests) > 1:
        notes.append("Adjusted p-values use Holm correction across the tests run.")
    status = "ok" if raw_tests else "insufficient_data"
    return {"status": status, "target": target,
            "message": None if raw_tests else "No usable grouping columns (need 2+ groups with at least 5 rows each).",
            "alpha": ALPHA, "tests": raw_tests, "skipped": skipped, "notes": notes,
            "timing_ms": {"compute_total": round((time.perf_counter() - t0) * 1000, 1)}}
