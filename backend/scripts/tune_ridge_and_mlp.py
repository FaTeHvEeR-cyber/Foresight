"""Hyperparameter tuning script for Ridge and MLPRegressor on Engine A dataset.

1. Evaluates Ridge Regression across alpha in [0.1, 1.0, 5.0, 10.0, 50.0].
2. Evaluates MLPRegressor across hidden_layer_sizes in [(32,), (64, 32), (100, 50), (64, 64)]
   and learning_rate_init in [0.001, 0.01].
3. Computes R^2, RMSPE (on y >= 50 subset of clean validation), MAE, RMSE.
4. Identifies and reports the best configuration for each model by R^2.
"""

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.neural_network import MLPRegressor

# Add backend directory to sys.path to import src modules
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.training.train_engine_a import (  # noqa: E402
    compute_rmspe,
    engineer_features,
    load_dataset,
    resolve_default_data_path,
    resolve_default_ground_truth_path,
    split_train_validation,
)


def run_tuning():
    print("=" * 85)
    print("      ENGINE A HYPERPARAMETER TUNING: RIDGE & MLPREGRESSOR")
    print("=" * 85)

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

    # Anomaly exclusion on validation fold
    print(f"[INFO] Loading ground truth anomalies from: {gt_path}")
    gt_df = pd.read_parquet(gt_path)
    gt_map = gt_df.set_index("row_index")["is_anomaly"].to_dict()

    val_is_anomaly = np.asarray(val_df["row_index"].map(gt_map.get).fillna(False), dtype=bool)
    val_clean_mask = np.logical_not(val_is_anomaly)

    total_val = len(val_df)
    clean_val_count = int(np.sum(val_clean_mask))
    anom_val_count = int(np.sum(val_is_anomaly))

    print(
        f"Validation summary: {total_val} total rows | {anom_val_count} anomalies "
        f"({(anom_val_count / total_val) * 100:.2f}%) | {clean_val_count} clean rows"
    )

    X_val_clean = X_val[val_clean_mask]
    y_val_clean = y_val[val_clean_mask]

    # Subset mask for y >= 50
    mask_ge50 = y_val_clean >= 50
    count_ge50 = int(np.sum(mask_ge50))
    count_lt50 = int(np.sum(~mask_ge50))
    print(
        f"Evaluation scope: {clean_val_count} clean rows total | "
        f"{count_ge50} rows with y >= 50 ({(count_ge50 / clean_val_count) * 100:.2f}%) | "
        f"{count_lt50} rows with y < 50 ({(count_lt50 / clean_val_count) * 100:.2f}%)"
    )

    # =========================================================================
    # PART 1: Ridge Hyperparameter Grid Search
    # =========================================================================
    print("\n" + "=" * 85)
    print("PART 1: RIDGE REGRESSION HYPERPARAMETER GRID (alpha: 0.1, 1.0, 5.0, 10.0, 50.0)")
    print("=" * 85)

    alphas = [0.1, 1.0, 5.0, 10.0, 50.0]
    ridge_results = []

    for alpha in alphas:
        ridge = Ridge(alpha=alpha, random_state=42)
        ridge.fit(X_train, y_train)

        pred_clean = np.clip(ridge.predict(X_val_clean), 0.0, None)

        r2 = float(r2_score(y_val_clean, pred_clean))
        mae = float(mean_absolute_error(y_val_clean, pred_clean))
        rmse = float(np.sqrt(mean_squared_error(y_val_clean, pred_clean)))

        # RMSPE evaluated strictly on clean rows where y >= 50
        rmspe_ge50 = compute_rmspe(y_val_clean[mask_ge50], pred_clean[mask_ge50])
        # Also compute overall clean RMSPE for full visibility
        rmspe_all = compute_rmspe(y_val_clean, pred_clean)

        ridge_results.append({
            "alpha": alpha,
            "r2": r2,
            "rmspe_ge50": rmspe_ge50,
            "rmspe_all": rmspe_all,
            "mae": mae,
            "rmse": rmse,
        })

    ridge_df = pd.DataFrame(ridge_results)
    ridge_df = ridge_df.sort_values(by="r2", ascending=False).reset_index(drop=True)

    print(f"\n{'alpha':>8} | {'R^2':>8} | {'RMSPE (y>=50)':>15} | {'RMSPE (All Clean)':>18} | {'MAE':>8} | {'RMSE':>8}")
    print("-" * 75)
    for _, row in ridge_df.iterrows():
        print(
            f"{row['alpha']:>8.1f} | "
            f"{row['r2']:>8.4f} | "
            f"{row['rmspe_ge50']:>14.2f}% | "
            f"{row['rmspe_all']:>17.2f}% | "
            f"{row['mae']:>8.2f} | "
            f"{row['rmse']:>8.2f}"
        )

    best_ridge = ridge_df.iloc[0]
    print(f"\n--> Best Ridge Config by R^2: alpha = {best_ridge['alpha']} (R^2 = {best_ridge['r2']:.4f}, RMSPE_ge50 = {best_ridge['rmspe_ge50']:.2f}%)")

    # =========================================================================
    # PART 2: MLPRegressor Hyperparameter Grid Search
    # =========================================================================
    print("\n" + "=" * 85)
    print("PART 2: MLPREGRESSOR HYPERPARAMETER GRID")
    print("        hidden_layer_sizes: (32,), (64, 32), (100, 50), (64, 64)")
    print("        learning_rate_init: 0.001, 0.01")
    print("=" * 85)

    hidden_layers_list = [(32,), (64, 32), (100, 50), (64, 64)]
    lr_inits = [0.001, 0.01]

    mlp_grid = list(itertools.product(hidden_layers_list, lr_inits))
    mlp_results = []

    print(f"\nRunning {len(mlp_grid)} MLP configurations...")

    for hidden_layers, lr_init in mlp_grid:
        mlp = MLPRegressor(
            hidden_layer_sizes=hidden_layers,
            learning_rate_init=lr_init,
            activation="relu",
            solver="adam",
            max_iter=400,
            random_state=42,
            early_stopping=True,
            validation_fraction=0.1,
        )
        mlp.fit(X_train, y_train)

        pred_clean = np.clip(mlp.predict(X_val_clean), 0.0, None)

        r2 = float(r2_score(y_val_clean, pred_clean))
        mae = float(mean_absolute_error(y_val_clean, pred_clean))
        rmse = float(np.sqrt(mean_squared_error(y_val_clean, pred_clean)))

        rmspe_ge50 = compute_rmspe(y_val_clean[mask_ge50], pred_clean[mask_ge50])
        rmspe_all = compute_rmspe(y_val_clean, pred_clean)

        mlp_results.append({
            "hidden_layers": str(hidden_layers),
            "lr_init": lr_init,
            "r2": r2,
            "rmspe_ge50": rmspe_ge50,
            "rmspe_all": rmspe_all,
            "mae": mae,
            "rmse": rmse,
            "n_iter": mlp.n_iter_,
        })

    mlp_df = pd.DataFrame(mlp_results)
    mlp_df = mlp_df.sort_values(by="r2", ascending=False).reset_index(drop=True)

    print(f"\n{'hidden_layers':<15} | {'lr_init':>8} | {'R^2':>8} | {'RMSPE (y>=50)':>15} | {'RMSPE (All Clean)':>18} | {'MAE':>8} | {'RMSE':>8} | {'iters':>6}")
    print("-" * 96)
    for _, row in mlp_df.iterrows():
        print(
            f"{row['hidden_layers']:<15} | "
            f"{row['lr_init']:>8.3f} | "
            f"{row['r2']:>8.4f} | "
            f"{row['rmspe_ge50']:>14.2f}% | "
            f"{row['rmspe_all']:>17.2f}% | "
            f"{row['mae']:>8.2f} | "
            f"{row['rmse']:>8.2f} | "
            f"{row['n_iter']:>6}"
        )

    best_mlp = mlp_df.iloc[0]
    print(
        f"\n--> Best MLP Config by R^2: hidden_layers = {best_mlp['hidden_layers']}, "
        f"lr_init = {best_mlp['lr_init']} (R^2 = {best_mlp['r2']:.4f}, RMSPE_ge50 = {best_mlp['rmspe_ge50']:.2f}%)"
    )

    # =========================================================================
    # PART 3: Summary of Best Performing Configurations
    # =========================================================================
    print("\n" + "=" * 85)
    print("PART 3: SUMMARY OF BEST CONFIGURATIONS ACROSS ALL ENGINE A MODELS")
    print("=" * 85)

    print(f"\n{'Model':<16} | {'Best Configuration':<32} | {'R^2':>8} | {'RMSPE (y>=50)':>15} | {'MAE':>8} | {'RMSE':>8}")
    print("-" * 96)
    print(
        f"{'Ridge':<16} | {'alpha=' + str(best_ridge['alpha']):<32} | "
        f"{best_ridge['r2']:>8.4f} | {best_ridge['rmspe_ge50']:>14.2f}% | {best_ridge['mae']:>8.2f} | {best_ridge['rmse']:>8.2f}"
    )
    print(
        f"{'MLP':<16} | {best_mlp['hidden_layers'] + ', lr=' + str(best_mlp['lr_init']):<32} | "
        f"{best_mlp['r2']:>8.4f} | {best_mlp['rmspe_ge50']:>14.2f}% | {best_mlp['mae']:>8.2f} | {best_mlp['rmse']:>8.2f}"
    )
    # Include tuned XGBoost from previous diagnostic for context
    print(
        f"{'XGBoost (from #1)':<16} | {'depth=3, n_est=100, lr=0.05':<32} | "
        f"{0.8949:>8.4f} | {13.56:>14.2f}% | {14.26:>8.2f} | {21.09:>8.2f}"
    )
    print("-" * 96)
    print("Target Thresholds: R^2 >= 0.85 | RMSPE <= 15.0% | XGBoost RMSPE < Ridge RMSPE")


if __name__ == "__main__":
    run_tuning()
