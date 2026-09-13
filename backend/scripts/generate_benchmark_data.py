import argparse
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


def generate_data(output_dir="."):
    """
    Generates a synthetic tabular dataset for demo-mode model training with
    injected anomalies, and saves features/target and ground truth to separate files.
    """
    # 4. Add a fixed random seed so this is reproducible across runs.
    np.random.seed(42)

    # Configuration
    n_stores = 50
    days_per_store = 120
    n_rows = n_stores * days_per_store
    start_date = datetime(2022, 1, 1)

    # 1. Generate a synthetic tabular dataset
    # We will generate daily data for multiple stores
    dates = [start_date + timedelta(days=i) for i in range(days_per_store)]
    store_ids = np.repeat(np.arange(1, n_stores + 1), days_per_store)
    date_list = np.tile(dates, n_stores)

    df = pd.DataFrame({
        "store_id": store_ids,
        "date": date_list
    })

    # Feature 1: day_of_week
    df['day_of_week'] = df['date'].dt.dayofweek

    # Feature 2: promo_flag (mostly on weekends or random)
    df['promo_flag'] = np.random.choice([0, 1], size=n_rows, p=[0.8, 0.2])

    # Feature 3: temperature (Seasonal temperature with some noise)
    day_of_year = df['date'].dt.dayofyear
    df['temperature'] = 15 + 10 * np.sin(2 * np.pi * day_of_year / 365.25) + np.random.normal(0, 3, n_rows)

    # Feature 4: competitor_distance (fixed per store)
    comp_dist = {s: np.random.uniform(0.5, 20.0) for s in range(1, n_stores + 1)}
    df['competitor_distance'] = df['store_id'].map(comp_dist)

    # Feature 5: store_type
    store_types = {s: np.random.choice(['Mall', 'Street', 'Strip']) for s in range(1, n_stores + 1)}
    df['store_type'] = df['store_id'].map(store_types)

    # Feature 6: region
    regions = {s: np.random.choice(['North', 'South', 'East', 'West']) for s in range(1, n_stores + 1)}
    df['region'] = df['store_id'].map(regions)

    # Feature 7: inventory_level
    df['inventory_level'] = np.random.randint(50, 1000, n_rows)

    # Feature 8: customer_rating
    ratings = {s: np.random.uniform(3.0, 5.0) for s in range(1, n_stores + 1)}
    df['customer_rating'] = df['store_id'].map(ratings)

    # Feature 9: local_holiday
    df['local_holiday'] = np.random.choice([0, 1], size=n_rows, p=[0.95, 0.05])

    # Target generation (units_sold)
    type_multiplier = {'Mall': 1.5, 'Street': 1.0, 'Strip': 1.2}
    base_sales = df['store_type'].map(type_multiplier) * 100

    # Multiplicative promo effect (+40%)
    promo_multiplier = np.where(df['promo_flag'] == 1, 1.4, 1.0)
    
    # Stronger weekend effect
    dow_effect = np.where(df['day_of_week'] >= 5, 60, 0)
    
    # Smoother non-linear temperature effect (optimal at 20C)
    temp_effect = -1.0 * (df['temperature'] - 20)**2 + 50
    
    # Multiplicative holiday spike (+80%)
    holiday_multiplier = np.where(df['local_holiday'] == 1, 1.8, 1.0)

    # Combine signals + reduced noise for target
    signal = (base_sales + dow_effect + temp_effect) * promo_multiplier * holiday_multiplier
    units_sold = signal + np.random.normal(0, 5, n_rows)

    # Strictly clip to > 0
    units_sold = np.clip(units_sold, 1, None)
    df['units_sold'] = np.round(units_sold).astype(int)

    # 2. Inject a KNOWN, LABELED set of anomalies at a calibrated ~5% contamination rate
    n_anomalies = int(n_rows * 0.05)
    anomaly_indices = np.random.choice(n_rows, n_anomalies, replace=False)

    df['is_anomaly'] = False
    df.loc[anomaly_indices, 'is_anomaly'] = True

    # Inject anomalies into target and some features
    for idx in anomaly_indices:
        anomaly_type = np.random.choice(['spike', 'drop', 'weird_temp'])
        if anomaly_type == 'spike':
            df.at[idx, 'units_sold'] = int(df.at[idx, 'units_sold'] * np.random.uniform(3, 6))
        elif anomaly_type == 'drop':
            df.at[idx, 'units_sold'] = max(1, int(df.at[idx, 'units_sold'] * np.random.uniform(0.01, 0.1)))
        elif anomaly_type == 'weird_temp':
            df.at[idx, 'temperature'] = float(np.random.uniform(40, 60)) # Extreme temp

    # Ensure clipping is respected after anomaly injection
    df['units_sold'] = np.clip(df['units_sold'], 1, None)
    df['units_sold'] = np.round(df['units_sold']).astype(int)

    # 3. Output two separate files to prevent label leakage
    features_target_df = df.drop(columns=['is_anomaly'])
    
    # Ground truth: row index + is_anomaly boolean
    ground_truth_df = df[['is_anomaly']].reset_index().rename(columns={'index': 'row_index'})

    os.makedirs(output_dir, exist_ok=True)
    benchmark_file = os.path.join(output_dir, "benchmark_data.parquet")
    gt_file = os.path.join(output_dir, "benchmark_data_ground_truth.parquet")

    # Save to parquet
    features_target_df.to_parquet(benchmark_file, index=False)
    ground_truth_df.to_parquet(gt_file, index=False)

    print(f"Generated {n_rows} rows of synthetic benchmark data.")
    print(f"Features and target saved to {benchmark_file}")
    print(f"Ground truth anomalies saved to {gt_file}")
    print(f"Total anomalies injected: {n_anomalies} ({(n_anomalies/n_rows)*100:.1f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic benchmark data")
    parser.add_argument(
        "--output-dir", 
        type=str, 
        default=os.path.join(os.path.dirname(__file__), "..", "data"), 
        help="Directory to save the parquet files"
    )
    args = parser.parse_args()
    
    generate_data(args.output_dir)
