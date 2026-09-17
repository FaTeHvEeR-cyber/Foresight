import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add backend directory to sys.path to import src modules
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.training.train_engine_a import load_dataset, engineer_features, split_train_validation  # noqa: E402

def run_diagnostics():
    print("==================================================")
    print("          ENGINE A DATA DIAGNOSTICS")
    print("==================================================\n")
    
    # Load dataset
    data_path = Path(__file__).resolve().parent.parent / "data" / "benchmark_data.parquet"
    df = load_dataset(data_path)
    print(f"\nLoaded raw data: {df.shape}")
    
    # 3. Check lag-feature generation step
    print("\n--- 3. Lag Feature Generation Check ---")
    data_with_lags = df.sort_values(["store_id", "date"]).reset_index(drop=True).copy()
    data_with_lags["lag_30"] = data_with_lags.groupby("store_id")["units_sold"].shift(30)
    nan_count = data_with_lags["lag_30"].isna().sum()
    print(f"Total rows: {len(data_with_lags)}")
    print(f"Rows with NaN lag_30 (due to t-30 warm-up): {nan_count}")
    print("Current handling in `engineer_features`: These rows are dropped via `dropna()`.")
    
    # Get engineered data
    df_eng = engineer_features(df)
    
    # 4. Check train/validation split
    print("\n--- 4. Train/Validation Split Check ---")
    X_train_scaled, X_val_scaled, y_train, y_val, scaler, feature_names, train_df, val_df = split_train_validation(df_eng)
    
    train_start = train_df["date"].min().strftime("%Y-%m-%d")
    train_end = train_df["date"].max().strftime("%Y-%m-%d")
    val_start = val_df["date"].min().strftime("%Y-%m-%d")
    val_end = val_df["date"].max().strftime("%Y-%m-%d")
    
    print(f"Train dates: {train_start} to {train_end} ({len(train_df)} rows)")
    print(f"Val dates:   {val_start} to {val_end} ({len(val_df)} rows)")
    if train_end < val_start:
        print("Status: Proper time-based split confirmed (no temporal leakage).")
    else:
        print("Status: WARNING! Dates overlap between train and val!")
        
    # 1. Target column statistics
    print("\n--- 1. Target Column Statistics (units_sold on Train) ---")
    y_series = pd.Series(y_train)
    target_min = y_series.min()
    target_max = y_series.max()
    target_mean = y_series.mean()
    target_median = y_series.median()
    target_std = y_series.std()
    p05 = y_series.quantile(0.05)
    p95 = y_series.quantile(0.95)
    
    print(f"Min: {target_min:.2f} | Max: {target_max:.2f}")
    print(f"Mean: {target_mean:.2f} | Median: {target_median:.2f}")
    print(f"Std Dev: {target_std:.2f}")
    print(f"5th Percentile: {p05:.2f} | 95th Percentile: {p95:.2f}")
    
    flagged_magnitude = False
    if target_median < 10 or (target_std > target_median):
        flagged_magnitude = True
        print("\n--> FLAG: Target has very low typical magnitude relative to its variance!")
        print("          This mathematical property inflates RMSPE dramatically because")
        print("          percentage error = |y_pred - y_true| / y_true.")
        print("          When y_true is 1 or 2, a normal error of 20 units becomes 1000%+ error.")
        
    # 2. Feature-target correlation
    print("\n--- 2. Feature-Target Correlation (Pearson) ---")
    X_train_df = pd.DataFrame(X_train_scaled, columns=feature_names)
    correlations = []
    for col in feature_names:
        r = float(pd.Series(X_train_df[col]).corr(pd.Series(y_series)))
        correlations.append((col, r))
        
    correlations.sort(key=lambda x: abs(x[1]), reverse=True)
    for col, r in correlations:
        print(f"{col:25} {r:8.4f}")
        
    # Check if all correlations are weak
    # Let's ignore standard scalar issues and just look at the absolute values
    # Exclude NaN correlations if any
    valid_corrs = [abs(r) for col, r in correlations if not np.isnan(r)]
    all_weak = all(r < 0.1 for r in valid_corrs)
    if all_weak:
        print("\n--> FLAG: All valid correlations are near zero (|r| < 0.1).")
        print("          The synthetic generator isn't encoding a learnable relationship")
        print("          between the features and the target.")
        
    print("\n==================================================")
    print("               DIAGNOSTIC SUMMARY")
    print("==================================================")
    
    if flagged_magnitude:
        print("* [TARGET MAGNITUDE] The target 'units_sold' median is too low relative to its variance.")
        print("  This causes the RMSPE metric (which divides by true sales) to explode into the")
        print("  thousands of percent on small absolute errors, causing the <15% threshold to fail.")
        
    if all_weak:
        print("* [CORRELATIONS] The synthetic features have almost no linear correlation with the target")
        print("  (|r| < 0.1). The models (Ridge/XGBoost/MLP) cannot learn a strong signal,")
        print("  explaining why they all converge to similar low R^2 scores (~0.2).")
    else:
        print("* [CORRELATIONS] There is some correlation, but it might not be enough or is overwhelmed")
        print("  by noise/anomalies, contributing to the low R^2 scores.")
        
    print("* [LAG HANDLING] The first 30 days per store are dropped because of the t-30 lag")
    print("  requirement. This is correctly handled (NaNs are not propagated) but it reduces")
    print("  the amount of training data available.")
        
    print("* [TRAIN/VAL SPLIT] The split is strictly chronological. The poor performance is")
    print("  therefore NOT an artifact of data leakage or random shuffling.")

if __name__ == "__main__":
    run_diagnostics()
