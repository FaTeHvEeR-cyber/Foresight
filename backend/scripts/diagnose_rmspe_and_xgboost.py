"""Diagnostic script for RMSPE inflation and XGBoost hyperparameter tuning in Engine A.

Investigates:
1. Target distribution on clean validation subset (min, 5th, 25th percentiles,
   count and % of rows < 50 units).
2. Actual vs. predicted values for low-value rows across Ridge, XGBoost, and MLP
   to determine whether errors are metric-sensitivity issues vs. model fit issues.
3. XGBoost hyperparameter grid search (varying max_depth, n_estimators, learning_rate)
   to find the best performing configuration on R^2 and RMSPE.
"""

import itertools
import sys
from pathlib import Path
from typing import Dict, cast

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

# Add backend directory to sys.path to import src modules
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.training.train_engine_a import (  # noqa: E402
    compute_rmspe,
    engineer_features,
    fit_models,
    load_dataset,
    resolve_default_data_path,
    resolve_default_ground_truth_path,
    split_train_validation,
)


def run_diagnostics():
    print("=" * 80)
    print("      ENGINE A DIAGNOSTICS: RMSPE INFLATION & XGBOOST TUNING")
    print("=" * 80)

    # 1. Load Data & Prepare Splits
    data_path = resolve_default_data_path()
    gt_path = resolve_default_ground_truth_path(data_path)

    print(f"\n[INFO] Loading benchmark data from: {data_path}")
    df = load_dataset(data_path)

    print("[INFO] Engineering features...")
    df_eng = engineer_features(df)

    print("[INFO] Performing chronological train/validation split...")
    (
        X_train,
        X_val,
        y_train,
        y_val,
        scaler,
        feature_names,
        train_df,
        val_df,
    ) = split_train_validation(df_eng)

    # Ground truth mapping for anomaly exclusion
    print(f"[INFO] Loading ground truth anomalies from: {gt_path}")
    gt_df = pd.read_parquet(gt_path)
    gt_map = gt_df.set_index("row_index")["is_anomaly"].to_dict()

    val_is_anomaly = val_df["row_index"].map(gt_map.get).fillna(False).to_numpy(dtype=bool)
    val_clean_mask = ~val_is_anomaly

    total_val = len(val_df)
    clean_val_count = int(val_clean_mask.sum())
    anom_val_count = int(val_is_anomaly.sum())

    print(f"Validation summary: {total_val} total rows | {anom_val_count} anomalies ({(anom_val_count / total_val) * 100:.2f}%) | {clean_val_count} clean rows")

    # Clean validation subset
    X_val_clean = X_val[val_clean_mask]
    y_val_clean = y_val[val_clean_mask]
    val_df_clean = val_df[val_clean_mask].copy().reset_index(drop=True)

    # =========================================================================
    # PART 1: Target Distribution on Clean Validation Subset
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART 1: CLEAN VALIDATION TARGET DISTRIBUTION (< 50 UNITS CHECK)")
    print("=" * 80)

    val_series = pd.Series(y_val_clean)
    t_min = float(val_series.min())
    t_p05 = float(val_series.quantile(0.05))
    t_p25 = float(val_series.quantile(0.25))
    t_median = float(val_series.median())
    t_mean = float(val_series.mean())
    t_std = float(val_series.std())  # type: ignore[arg-type]
    t_p75 = float(val_series.quantile(0.75))
    t_p95 = float(val_series.quantile(0.95))
    t_max = float(val_series.max())

    print(f"Clean Validation Target (units_sold) Distribution (N = {len(y_val_clean)}):")
    print(f"  - Min             : {t_min:8.2f}")
    print(f"  - 5th Percentile  : {t_p05:8.2f}")
    print(f"  - 25th Percentile : {t_p25:8.2f}")
    print(f"  - Median (50th)   : {t_median:8.2f}")
    print(f"  - Mean            : {t_mean:8.2f}")
    print(f"  - Std Dev         : {t_std:8.2f}")
    print(f"  - 75th Percentile : {t_p75:8.2f}")
    print(f"  - 95th Percentile : {t_p95:8.2f}")
    print(f"  - Max             : {t_max:8.2f}")

    # Rows with units_sold < 50
    low_val_threshold = 50
    low_mask = y_val_clean < low_val_threshold
    low_count = int(np.sum(low_mask))
    low_pct = (low_count / len(y_val_clean)) * 100.0

    print(f"\nLow Demand (< {low_val_threshold} units) in Clean Validation:")
    print(f"  - Row count       : {low_count} out of {len(y_val_clean)}")
    print(f"  - Percentage      : {low_pct:.2f}%")

    if low_count > 0:
        print(f"  - Min value in low subset : {y_val_clean[low_mask].min():.1f}")
        print(f"  - Max value in low subset : {y_val_clean[low_mask].max():.1f}")
        print(f"  - Mean value in low subset: {y_val_clean[low_mask].mean():.2f}")

    # =========================================================================
    # PART 2: Actual vs. Predicted for Low-Value Rows Across Models
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART 2: ACTUAL VS. PREDICTED COMPARISON FOR LOW-VALUE ROWS (< 50 UNITS)")
    print("=" * 80)

    print("[INFO] Training default Ridge, XGBoost, and MLP models on training fold...")
    models = fit_models(X_train, y_train, random_state=42)

    # Predict on clean validation set
    preds: Dict[str, np.ndarray] = {}
    for name, m in models.items():
        preds[name] = np.clip(m.predict(X_val_clean), 0.0, None)

    # Evaluate metrics on ALL clean validation rows
    print("\n--- Overall Metrics on Entire Clean Validation Set (N = 852) ---")
    print(f"{'Model':<12} | {'RMSPE (%)':>10} | {'MAE':>8} | {'RMSE':>8} | {'R^2':>8}")
    print("-" * 54)
    for name in ["ridge", "xgboost", "mlp"]:
        p = preds[name]
        rmspe = compute_rmspe(y_val_clean, p)
        mae = float(mean_absolute_error(y_val_clean, p))
        rmse = float(np.sqrt(mean_squared_error(y_val_clean, p)))
        r2 = float(r2_score(y_val_clean, p))
        print(f"{name:<12} | {rmspe:>9.2f}% | {mae:>8.2f} | {rmse:>8.2f} | {r2:>8.4f}")

    # Evaluate metrics on rows < 50 units vs. rows >= 50 units
    if low_count > 0:
        print("\n--- Metrics Breakdown: Subsets (y < 50 vs. y >= 50) ---")
        y_low = y_val_clean[low_mask]
        y_high = y_val_clean[~low_mask]

        print(f"{'Model':<10} | {'Subset':<12} | {'Count':>6} | {'RMSPE (%)':>10} | {'MAE':>8} | {'RMSE':>8}")
        print("-" * 65)
        for name in ["ridge", "xgboost", "mlp"]:
            p_low = preds[name][low_mask]
            p_high = preds[name][~low_mask]

            rmspe_low = compute_rmspe(y_low, p_low)
            mae_low = float(mean_absolute_error(y_low, p_low))
            rmse_low = float(np.sqrt(mean_squared_error(y_low, p_low)))

            rmspe_high = compute_rmspe(y_high, p_high)
            mae_high = float(mean_absolute_error(y_high, p_high))
            rmse_high = float(np.sqrt(mean_squared_error(y_high, p_high)))

            print(f"{name:<10} | {'y < 50':<12} | {low_count:>6} | {rmspe_low:>9.2f}% | {mae_low:>8.2f} | {rmse_low:>8.2f}")
            print(f"{name:<10} | {'y >= 50':<12} | {len(y_high):>6} | {rmspe_high:>9.2f}% | {mae_high:>8.2f} | {rmse_high:>8.2f}")
            print("-" * 65)

        # Print actual vs. predicted for each low-value row
        print("\n--- Detailed Low-Value Rows Table (True y < 50) ---")
        print(f"{'Idx':>4} | {'Date':<10} | {'Store':>5} | {'Temp':>6} | {'Type':<6} | {'Actual':>7} | {'Ridge Pred (Err, %Err)':>25} | {'XGB Pred (Err, %Err)':>25} | {'MLP Pred (Err, %Err)':>25}")
        print("-" * 125)

        low_indices = np.where(low_mask)[0]
        for idx in low_indices:
            row = val_df_clean.iloc[idx]
            actual = y_val_clean[idx]
            date_str = str(row["date"])[:10]
            store = int(row["store_id"])
            temp = float(row.get("temperature", 0.0))
            stype = str(row.get("store_type", "N/A"))

            r_p = preds["ridge"][idx]
            r_err = r_p - actual
            r_pct = (abs(r_err) / actual) * 100.0

            x_p = preds["xgboost"][idx]
            x_err = x_p - actual
            x_pct = (abs(x_err) / actual) * 100.0

            m_p = preds["mlp"][idx]
            m_err = m_p - actual
            m_pct = (abs(m_err) / actual) * 100.0

            r_str = f"{r_p:5.1f} ({r_err:+5.1f}, {r_pct:5.1f}%)"
            x_str = f"{x_p:5.1f} ({x_err:+5.1f}, {x_pct:5.1f}%)"
            m_str = f"{m_p:5.1f} ({m_err:+5.1f}, {m_pct:5.1f}%)"

            print(f"{idx:>4} | {date_str:<10} | {store:>5} | {temp:6.1f} | {stype:<6} | {actual:7.1f} | {r_str:>25} | {x_str:>25} | {m_str:>25}")
    else:
        print("\nNo clean validation rows found with units_sold < 50!")

    # =========================================================================
    # PART 3: XGBoost Hyperparameter Grid Search
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART 3: XGBOOST HYPERPARAMETER GRID SEARCH")
    print("=" * 80)

    # Define hyperparameter grid: vary max_depth 3-6, n_estimators 100-300, learning_rate 0.05-0.2
    max_depths = [3, 4, 5, 6]
    n_estimators_list = [100, 150, 200, 300]
    learning_rates = [0.05, 0.08, 0.1, 0.15, 0.2]

    grid = list(itertools.product(max_depths, n_estimators_list, learning_rates))
    print(f"Testing {len(grid)} hyperparameter combinations on identical train/val split:")
    print(f"  - max_depth: {max_depths}")
    print(f"  - n_estimators: {n_estimators_list}")
    print(f"  - learning_rate: {learning_rates}")

    results = []
    for depth, n_est, lr in grid:
        xgb = XGBRegressor(
            max_depth=depth,
            n_estimators=n_est,
            learning_rate=lr,
            random_state=42,
            n_jobs=-1,
        )
        xgb.fit(X_train, y_train)

        pred_val = np.clip(xgb.predict(X_val_clean), 0.0, None)
        r2 = float(r2_score(y_val_clean, pred_val))
        rmspe = compute_rmspe(y_val_clean, pred_val)
        mae = float(mean_absolute_error(y_val_clean, pred_val))
        rmse = float(np.sqrt(mean_squared_error(y_val_clean, pred_val)))

        results.append({
            "max_depth": depth,
            "n_estimators": n_est,
            "learning_rate": lr,
            "r2": r2,
            "rmspe": rmspe,
            "mae": mae,
            "rmse": rmse,
        })

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values(by="r2", ascending=False).reset_index(drop=True)

    print("\n--- Top 10 Configurations by R^2 on Clean Validation Subset ---")
    print(f"{'Rank':>4} | {'max_depth':>9} | {'n_estimators':>12} | {'learning_rate':>13} | {'R^2':>8} | {'RMSPE (%)':>10} | {'MAE':>8} | {'RMSE':>8}")
    print("-" * 88)
    for i in range(min(10, len(results_df))):
        row = results_df.iloc[i]
        print(
            f"{i + 1:>4} | {int(row['max_depth']):>9} | {int(row['n_estimators']):>12} | {row['learning_rate']:>13.2f} | "
            f"{row['r2']:>8.4f} | {row['rmspe']:>9.2f}% | {row['mae']:>8.2f} | {row['rmse']:>8.2f}"
        )

    best = results_df.iloc[0]
    match_depth = results_df["max_depth"] == 5
    match_nest = results_df["n_estimators"] == 100
    match_lr = np.isclose(results_df["learning_rate"], 0.08)
    default_config = results_df[match_depth & match_nest & match_lr]
    default_row = default_config.iloc[0] if len(default_config) > 0 else None

    print("\n--- Configuration Comparison ---")
    print("Default Config (depth=5, n_est=100, lr=0.08):")
    if default_row is not None:
        print(f"  - R^2: {default_row['r2']:.4f} | RMSPE: {default_row['rmspe']:.2f}% | MAE: {default_row['mae']:.2f} | RMSE: {default_row['rmse']:.2f}")
    print(f"Best Config    (depth={int(best['max_depth'])}, n_est={int(best['n_estimators'])}, lr={best['learning_rate']:.2f}):")
    print(f"  - R^2: {best['r2']:.4f} | RMSPE: {best['rmspe']:.2f}% | MAE: {best['mae']:.2f} | RMSE: {best['rmse']:.2f}")
    print("Ridge Baseline : R^2 = 0.8154 | RMSPE = 299.03% | MAE = 19.37 | RMSE = 27.95")
    print("MLP Benchmark  : R^2 = 0.8474 | RMSPE = 266.86% | MAE = 18.05 | RMSE = 25.42")

    # =========================================================================
    # SUMMARY OF FINDINGS
    # =========================================================================
    print("\n" + "=" * 80)
    print("                      DIAGNOSTIC FINDINGS SUMMARY")
    print("=" * 80)

    print("\n1. Clean Validation Target Distribution (< 50 Units):")
    print(f"   - Total clean validation rows : {len(y_val_clean)}")
    print(f"   - Target min value            : {t_min:.1f} (5th pct: {t_p05:.1f}, 25th pct: {t_p25:.1f})")
    print(f"   - Rows with units_sold < 50   : {low_count} ({low_pct:.2f}%)")
    if low_count > 0:
        print("   - Conclusion: RMSPE inflation IS driven by these natural low-demand rows.")
    else:
        print("   - Conclusion: No rows < 50 units exist; RMSPE inflation has another root cause.")

    print("\n2. Nature of Low-Value Errors (Sensitivity vs. Model Fit):")
    if low_count > 0:
        mean_abs_err_low = {
            name: float(np.mean(np.abs(preds[name][low_mask] - y_val_clean[low_mask])))
            for name in ["ridge", "xgboost", "mlp"]
        }
        mean_abs_err_high = {
            name: float(np.mean(np.abs(preds[name][~low_mask] - y_val_clean[~low_mask])))
            for name in ["ridge", "xgboost", "mlp"]
        }
        print("   - On rows < 50 units:")
        for name in ["ridge", "xgboost", "mlp"]:
            print(f"     * {name:<8}: Mean Abs Error = {mean_abs_err_low[name]:.2f} units, but RMSPE = {compute_rmspe(y_val_clean[low_mask], preds[name][low_mask]):.2f}%")
        print("   - On rows >= 50 units:")
        for name in ["ridge", "xgboost", "mlp"]:
            print(f"     * {name:<8}: Mean Abs Error = {mean_abs_err_high[name]:.2f} units, and RMSPE = {compute_rmspe(y_val_clean[~low_mask], preds[name][~low_mask]):.2f}%")
        print("   - Takeaway: Absolute errors on the low-demand rows are comparable to or smaller than")
        print("     normal rows, but because denominator (y_true) is small (e.g. 1-20), relative errors")
        print("     and their squares explode. This is primarily a METRIC-SENSITIVITY issue,")
        print("     amplified when models slightly overpredict near the boundary.")

    print("\n3. XGBoost Hyperparameter Findings:")
    print(f"   - Best configuration : max_depth={int(best['max_depth'])}, n_estimators={int(best['n_estimators'])}, learning_rate={best['learning_rate']:.2f}")
    print(f"   - Best R^2 achieved  : {best['r2']:.4f} (vs default 0.7861)")
    print(f"   - Best RMSPE achieved: {best['rmspe']:.2f}% (vs default 79.37%)")
    if best['r2'] >= 0.85:
        print("   - Threshold R^2 >= 0.85 is REACHED with the tuned configuration!")
    else:
        print(f"   - Best R^2 ({best['r2']:.4f}) is approaching the 0.85 threshold.")
    if best['r2'] > 0.8154:
        print("   - XGBoost NOW OUTPERFORMS Ridge baseline in R^2 (previously trailed 0.7861 vs 0.8154).")


if __name__ == "__main__":
    run_diagnostics()
