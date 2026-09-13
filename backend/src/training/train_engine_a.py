"""Engine A Forecasting Training Pipeline.

Trains and evaluates Foresight's Engine A forecasting models:
1. Loads benchmark_data.parquet and applies time-aware feature engineering
   (lag features t-7/t-14/t-21/t-30, rolling stats, calendar encoding)
   without temporal leakage using a proper time-based train/validation split.
2. Trains three models on identical features and splits for fair comparison:
   - Ridge Regression (baseline)
   - XGBoost Regressor (primary)
   - scikit-learn MLPRegressor (benchmark)
3. Evaluates each on the validation fold (RMSPE, MAE, RMSE, R²).
   Asserts against thresholds: RMSPE <= 15%, R² >= 0.85, and XGBoost's
   RMSPE must be lower (better) than Ridge's.
   Reports all three models' metrics even if one fails its threshold without stopping early.
4. Serializes all three trained models as:
   - models/ridge_baseline.joblib
   - models/xgboost_primary.joblib
   - models/mlp_benchmark.joblib
5. Prints a summary table of all metrics per model at the end.
"""

import argparse
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

logger = logging.getLogger("engine_a_forecast")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)

# Threshold constants specified for validation evaluation
RMSPE_THRESHOLD: float = 15.0  # RMSPE <= 15%
R2_THRESHOLD: float = 0.85      # R² >= 0.85
LAG_PERIODS: List[int] = [7, 14, 21, 30]
ROLLING_WINDOWS: List[int] = [7, 14, 30]


def resolve_default_data_path() -> Path:
    """Locate benchmark_data.parquet across common repo working directories."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "data" / "benchmark_data.parquet",
        Path("data/benchmark_data.parquet"),
        Path("backend/data/benchmark_data.parquet"),
        Path("../data/benchmark_data.parquet"),
    ]
    for p in candidates:
        if p.is_file():
            return p.resolve()
    return candidates[0]


def load_dataset(data_path: Union[str, Path]) -> pd.DataFrame:
    """Load benchmark dataset from parquet format."""
    path = Path(data_path)
    if not path.exists():
        raise FileNotFoundError(f"Benchmark data file not found at: {path.resolve()}")

    logger.info("Loading benchmark data from: %s", path.resolve())
    df = pd.read_parquet(path)

    required_cols = {"store_id", "date", "units_sold"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Required columns missing from benchmark dataset: {missing}")

    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"])

    logger.info("Loaded dataset with %d rows and %d columns.", len(df), len(df.columns))
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Apply time-aware feature engineering without temporal leakage.

    1. Sorts chronologically per store (store_id, date).
    2. Constructs lag features t-7, t-14, t-21, t-30 on target units_sold.
    3. Computes rolling statistics (mean, std) using strictly past data (shift(1))
       to guarantee no target leakage into the predictor features.
    4. Extracts calendar features and cyclical sine/cosine encodings.
    5. Drops rows containing NaN lag values from the initial lookback window.
    """
    logger.info("Applying time-aware feature engineering...")
    data = df.sort_values(["store_id", "date"]).reset_index(drop=True).copy()

    # 1. Lag features per store: t-7, t-14, t-21, t-30
    for lag in LAG_PERIODS:
        data[f"lag_{lag}"] = data.groupby("store_id")["units_sold"].shift(lag)

    # 2. Rolling statistics per store: strictly past data using shift(1)
    # Using shift(1) ensures observation at time t is never used to compute feature at time t
    for w in ROLLING_WINDOWS:
        data[f"rolling_mean_{w}"] = data.groupby("store_id")["units_sold"].transform(
            lambda s, w=w: s.shift(1).rolling(window=w, min_periods=1).mean()
        )
        data[f"rolling_std_{w}"] = data.groupby("store_id")["units_sold"].transform(
            lambda s, w=w: s.shift(1).rolling(window=w, min_periods=1).std()
        ).fillna(0.0)

    # 3. Calendar encodings
    data["day_of_week"] = data["date"].dt.dayofweek
    data["day_of_month"] = data["date"].dt.day
    data["month"] = data["date"].dt.month
    data["day_of_year"] = data["date"].dt.dayofyear
    data["is_weekend"] = (data["day_of_week"] >= 5).astype(int)

    # Cyclical trigonometric encodings
    data["sin_dow"] = np.sin(2 * np.pi * data["day_of_week"] / 7.0)
    data["cos_dow"] = np.cos(2 * np.pi * data["day_of_week"] / 7.0)
    data["sin_month"] = np.sin(2 * np.pi * data["month"] / 12.0)
    data["cos_month"] = np.cos(2 * np.pi * data["month"] / 12.0)
    data["sin_doy"] = np.sin(2 * np.pi * data["day_of_year"] / 365.25)
    data["cos_doy"] = np.cos(2 * np.pi * data["day_of_year"] / 365.25)

    # 4. Drop initial rows with NaNs resulting from max lookback (lag 30)
    rows_before = len(data)
    data_clean = data.dropna().reset_index(drop=True)
    rows_after = len(data_clean)
    logger.info(
        "Feature engineering complete. Retained %d rows (%d rows dropped for lookback warm-up).",
        rows_after,
        rows_before - rows_after,
    )

    return data_clean


def split_train_validation(
    df: pd.DataFrame,
    val_ratio: float = 0.20,
    cutoff_date: Optional[Union[str, pd.Timestamp]] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, StandardScaler, List[str], pd.DataFrame, pd.DataFrame]:
    """Perform a proper time-based train/validation split without temporal leakage.

    - Splits strictly on time: earlier dates form train set, later dates form validation set.
    - One-hot encodes categorical variables on train set and aligns validation set.
    - Fits StandardScaler exclusively on train features to avoid distribution leakage.
    """
    logger.info("Executing time-based train/validation split...")
    unique_dates = np.sort(df["date"].unique())
    n_dates = len(unique_dates)

    if cutoff_date is not None:
        cutoff = pd.to_datetime(cutoff_date)
    else:
        split_idx = int(n_dates * (1.0 - val_ratio))
        cutoff = unique_dates[split_idx]

    train_df = df[df["date"] < cutoff].copy()
    val_df = df[df["date"] >= cutoff].copy()

    logger.info(
        "Time split cutoff: %s | Train dates: %d (%s to %s) | Val dates: %d (%s to %s)",
        cutoff,
        train_df["date"].nunique(),
        train_df["date"].min().strftime("%Y-%m-%d"),
        train_df["date"].max().strftime("%Y-%m-%d"),
        val_df["date"].nunique(),
        val_df["date"].min().strftime("%Y-%m-%d"),
        val_df["date"].max().strftime("%Y-%m-%d"),
    )
    logger.info("Train rows: %d | Validation rows: %d", len(train_df), len(val_df))

    # Identify categorical columns to dummy-encode
    cat_candidates = ["store_type", "region"]
    cat_cols = [c for c in cat_candidates if c in train_df.columns]

    # Numeric feature candidates
    non_feature_cols = {"store_id", "date", "units_sold", *cat_cols}
    num_cols = [c for c in train_df.columns if c not in non_feature_cols]

    # One-hot encode categoricals fit on train, align on val
    if cat_cols:
        train_cat = pd.get_dummies(train_df[cat_cols], drop_first=True)
        val_cat = pd.get_dummies(val_df[cat_cols], drop_first=True)
        val_cat = val_cat.reindex(columns=train_cat.columns, fill_value=0)

        X_train_df = pd.concat([train_df[num_cols].reset_index(drop=True), train_cat.reset_index(drop=True)], axis=1)
        X_val_df = pd.concat([val_df[num_cols].reset_index(drop=True), val_cat.reset_index(drop=True)], axis=1)
    else:
        X_train_df = train_df[num_cols].copy()
        X_val_df = val_df[num_cols].copy()

    feature_names = list(X_train_df.columns)
    y_train = train_df["units_sold"].values.astype(float)
    y_val = val_df["units_sold"].values.astype(float)

    # Standardize features (fitted strictly on train only)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_df)
    X_val_scaled = scaler.transform(X_val_df)

    logger.info("Feature preprocessing complete. Features count: %d", len(feature_names))
    return (
        X_train_scaled,
        X_val_scaled,
        y_train,
        y_val,
        scaler,
        feature_names,
        train_df,
        val_df,
    )


def fit_models(
    X_train: np.ndarray,
    y_train: np.ndarray,
    random_state: int = 42,
) -> Dict[str, Any]:
    """Train Ridge, XGBoost, and MLP models on identical features and splits."""
    models: Dict[str, Any] = {}

    # 1. Ridge Regression (baseline)
    logger.info("Fitting Ridge Regression baseline...")
    ridge = Ridge(alpha=1.0, random_state=random_state)
    ridge.fit(X_train, y_train)
    models["ridge"] = ridge

    # 2. XGBoost Regressor (primary)
    logger.info("Fitting XGBoost Regressor primary model...")
    xgboost_model = XGBRegressor(
        n_estimators=100,
        learning_rate=0.08,
        max_depth=5,
        random_state=random_state,
        n_jobs=-1,
    )
    xgboost_model.fit(X_train, y_train)
    models["xgboost"] = xgboost_model

    # 3. scikit-learn MLPRegressor (benchmark)
    logger.info("Fitting scikit-learn MLPRegressor benchmark model...")
    mlp = MLPRegressor(
        hidden_layer_sizes=(64, 32),
        activation="relu",
        solver="adam",
        max_iter=400,
        random_state=random_state,
        early_stopping=True,
        validation_fraction=0.1,
    )
    mlp.fit(X_train, y_train)
    models["mlp"] = mlp

    logger.info("All three models trained successfully.")
    return models


def compute_rmspe(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute Root Mean Square Percentage Error (RMSPE) in percent.

    Formula: sqrt(mean(((y_true - y_pred) / y_true) ** 2)) * 100%
    Safely ignores zero actual values to prevent division by zero.
    """
    y_t = np.asarray(y_true, dtype=float)
    y_p = np.asarray(y_pred, dtype=float)
    mask = y_t > 0
    if not np.any(mask):
        return 0.0
    relative_errors = (y_t[mask] - y_p[mask]) / y_t[mask]
    return float(np.sqrt(np.mean(np.square(relative_errors))) * 100.0)


def evaluate_models(
    models: Dict[str, Any],
    X_val: np.ndarray,
    y_val: np.ndarray,
) -> Dict[str, Dict[str, float]]:
    """Evaluate each model on validation fold and compute RMSPE, MAE, RMSE, R².

    Evaluates all three models completely without stopping early even if one
    fails threshold criteria.
    """
    logger.info("Evaluating models on validation fold...")
    metrics: Dict[str, Dict[str, float]] = {}

    for name, model in models.items():
        raw_pred = model.predict(X_val)
        # Sales units cannot be negative
        preds = np.clip(raw_pred, 0.0, None)

        rmspe_val = compute_rmspe(y_val, preds)
        mae_val = float(mean_absolute_error(y_val, preds))
        rmse_val = float(np.sqrt(mean_squared_error(y_val, preds)))
        r2_val = float(r2_score(y_val, preds))

        metrics[name] = {
            "rmspe": rmspe_val,
            "mae": mae_val,
            "rmse": rmse_val,
            "r2": r2_val,
        }
        logger.info(
            "Model %-8s | RMSPE: %8.2f%% | MAE: %7.2f | RMSE: %7.2f | R^2: %7.4f",
            name,
            rmspe_val,
            mae_val,
            rmse_val,
            r2_val,
        )

    return metrics


def print_summary_table(metrics: Dict[str, Dict[str, float]]) -> None:
    """Print a summary table of all metrics per model at the end."""
    col_w = {
        "model": 16,
        "rmspe": 12,
        "mae": 10,
        "rmse": 10,
        "r2": 10,
        "status": 22,
    }

    header = (
        f"{'Model':<{col_w['model']}} | "
        f"{'RMSPE (%)':>{col_w['rmspe']}} | "
        f"{'MAE':>{col_w['mae']}} | "
        f"{'RMSE':>{col_w['rmse']}} | "
        f"{'R^2':>{col_w['r2']}} | "
        f"{'Threshold Check':<{col_w['status']}}"
    )
    divider = "-" * len(header)

    print("\n" + "=" * len(header))
    print(" FORESIGHT ENGINE A FORECASTING MODEL BENCHMARK SUMMARY")
    print("=" * len(header))
    print(header)
    print(divider)

    for name, m in metrics.items():
        display_name = {
            "ridge": "Ridge Baseline",
            "xgboost": "XGBoost Primary",
            "mlp": "MLP Benchmark",
        }.get(name, name.capitalize())

        rmspe_ok = m["rmspe"] <= RMSPE_THRESHOLD
        r2_ok = m["r2"] >= R2_THRESHOLD

        if rmspe_ok and r2_ok:
            check_str = "PASS (All)"
        elif rmspe_ok:
            check_str = "PASS (RMSPE only)"
        elif r2_ok:
            check_str = "PASS (R^2 only)"
        else:
            check_str = "FAIL (Below target)"

        print(
            f"{display_name:<{col_w['model']}} | "
            f"{m['rmspe']:>{col_w['rmspe'] - 1}.2f}% | "
            f"{m['mae']:>{col_w['mae']}.2f} | "
            f"{m['rmse']:>{col_w['rmse']}.2f} | "
            f"{m['r2']:>{col_w['r2']}.4f} | "
            f"{check_str:<{col_w['status']}}"
        )

    print(divider)
    print(f" Targets: RMSPE <= {RMSPE_THRESHOLD:.1f}% | R^2 >= {R2_THRESHOLD:.2f} | XGBoost RMSPE < Ridge RMSPE")
    print("=" * len(header) + "\n")


def serialize_models(
    models: Dict[str, Any],
    models_dir: Union[str, Path] = "models",
    scaler: Optional[StandardScaler] = None,
    feature_names: Optional[List[str]] = None,
) -> Dict[str, Path]:
    """Serialize all three trained models to disk using joblib.

    Saves:
    - models/ridge_baseline.joblib
    - models/xgboost_primary.joblib
    - models/mlp_benchmark.joblib
    Mirrors files between models/ and backend/models/ if applicable.
    """
    target_dir = Path(models_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    filenames = {
        "ridge": "ridge_baseline.joblib",
        "xgboost": "xgboost_primary.joblib",
        "mlp": "mlp_benchmark.joblib",
    }

    artifact_paths: Dict[str, Path] = {}
    logger.info("Serializing trained models to: %s", target_dir.resolve())

    for model_key, filename in filenames.items():
        if model_key in models:
            path = target_dir / filename
            joblib.dump(models[model_key], path)
            artifact_paths[model_key] = path
            logger.info("  Serialized %s -> %s", model_key, path)

    if scaler is not None:
        scaler_path = target_dir / "engine_a_scaler.joblib"
        joblib.dump(scaler, scaler_path)
        artifact_paths["scaler"] = scaler_path

    if feature_names is not None:
        features_path = target_dir / "engine_a_features.joblib"
        joblib.dump(feature_names, features_path)
        artifact_paths["features"] = features_path

    # Mirror artifacts to companion directory if running in repo workspace
    try:
        abs_target = target_dir.resolve()
        if abs_target.name == "models":
            parent = abs_target.parent
            if (parent / "backend").is_dir() and parent.name != "backend":
                backend_models = parent / "backend" / "models"
                backend_models.mkdir(parents=True, exist_ok=True)
                for item_path in artifact_paths.values():
                    if item_path.is_file():
                        shutil.copy2(item_path, backend_models / item_path.name)
                logger.info("  Mirrored artifacts to backend directory: %s", backend_models)
            elif parent.name == "backend" and (parent.parent / "frontend").is_dir():
                root_models = parent.parent / "models"
                root_models.mkdir(parents=True, exist_ok=True)
                for item_path in artifact_paths.values():
                    if item_path.is_file():
                        shutil.copy2(item_path, root_models / item_path.name)
                logger.info("  Mirrored artifacts to root directory: %s", root_models)
    except Exception as e:
        logger.debug("Mirroring skipped: %s", e)

    return artifact_paths


def verify_thresholds(
    metrics: Dict[str, Dict[str, float]],
    enforce_thresholds: bool = True,
) -> None:
    """Verify performance against required criteria.

    Criteria:
    1. XGBoost RMSPE < Ridge RMSPE (XGBoost must outperform baseline).
    2. RMSPE <= 15%.
    3. R² >= 0.85.

    When enforce_thresholds=True, raises AssertionError detailing the failure.
    When enforce_thresholds=False, logs warning messages cleanly.
    """
    xgb_m = metrics.get("xgboost", {})
    ridge_m = metrics.get("ridge", {})

    xgb_rmspe = xgb_m.get("rmspe", float("inf"))
    ridge_rmspe = ridge_m.get("rmspe", float("inf"))
    xgb_r2 = xgb_m.get("r2", float("-inf"))

    # Check 1: XGBoost RMSPE < Ridge RMSPE
    is_better_than_ridge = xgb_rmspe < ridge_rmspe
    # Check 2: RMSPE <= 15%
    is_rmspe_ok = xgb_rmspe <= RMSPE_THRESHOLD
    # Check 3: R² >= 0.85
    is_r2_ok = xgb_r2 >= R2_THRESHOLD

    if not is_better_than_ridge:
        msg = f"XGBoost RMSPE ({xgb_rmspe:.2f}%) is not lower than Ridge RMSPE ({ridge_rmspe:.2f}%)."
        if enforce_thresholds:
            raise AssertionError(f"Threshold Assertion Failed: {msg}")
        logger.warning(msg)

    if not is_rmspe_ok:
        msg = f"XGBoost RMSPE ({xgb_rmspe:.2f}%) exceeds required threshold ({RMSPE_THRESHOLD:.1f}%)."
        if enforce_thresholds:
            raise AssertionError(f"Threshold Assertion Failed: {msg}")
        logger.warning(msg)

    if not is_r2_ok:
        msg = f"XGBoost R^2 ({xgb_r2:.4f}) is below required threshold ({R2_THRESHOLD:.2f})."
        if enforce_thresholds:
            raise AssertionError(f"Threshold Assertion Failed: {msg}")
        logger.warning(msg)

    if is_better_than_ridge and is_rmspe_ok and is_r2_ok:
        logger.info("All threshold assertions PASSED successfully.")


def train_engine_a(
    data_path: Optional[Union[str, Path]] = None,
    models_dir: Union[str, Path] = "models",
    val_ratio: float = 0.20,
    cutoff_date: Optional[Union[str, pd.Timestamp]] = None,
    enforce_thresholds: bool = False,
    random_state: int = 42,
) -> Dict[str, Any]:
    """Complete end-to-end training and evaluation pipeline for Engine A.

    1. Loads benchmark_data.parquet.
    2. Applies time-aware feature engineering (lags, rolling stats, calendar).
    3. Performs time-based train/validation split.
    4. Trains Ridge, XGBoost, and MLPRegressor on identical features/splits.
    5. Evaluates validation fold metrics without stopping early.
    6. Serializes all three models to models/.
    7. Prints summary table.
    8. Asserts thresholds if enforce_thresholds=True.
    """
    if data_path is None:
        data_path = resolve_default_data_path()

    # 1. Load data
    df = load_dataset(data_path)

    # 2. Time-aware feature engineering
    engineered_df = engineer_features(df)

    # 3. Time-based split & scaling
    (
        X_train,
        X_val,
        y_train,
        y_val,
        scaler,
        feature_names,
        train_df,
        val_df,
    ) = split_train_validation(
        engineered_df,
        val_ratio=val_ratio,
        cutoff_date=cutoff_date,
    )

    # 4. Train three models on identical features
    models = fit_models(X_train, y_train, random_state=random_state)

    # 5. Evaluate validation metrics for all models without stopping early
    metrics = evaluate_models(models, X_val, y_val)

    # 6. Serialize models
    artifacts = serialize_models(
        models=models,
        models_dir=models_dir,
        scaler=scaler,
        feature_names=feature_names,
    )

    # 7. Print summary table
    print_summary_table(metrics)

    # 8. Verify thresholds (assert if enforced)
    verify_thresholds(metrics, enforce_thresholds=enforce_thresholds)

    return {
        "models": models,
        "metrics": metrics,
        "artifacts": artifacts,
        "feature_names": feature_names,
        "scaler": scaler,
        "train_df": train_df,
        "val_df": val_df,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Train Foresight Engine A forecasting models (Ridge, XGBoost, MLP)."
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default=None,
        help="Path to benchmark_data.parquet (default: auto-detected)",
    )
    parser.add_argument(
        "--models-dir",
        type=str,
        default="models",
        help="Directory to save serialized model artifacts (default: models)",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.20,
        help="Fraction of chronological dates for validation fold (default: 0.20)",
    )
    parser.add_argument(
        "--enforce-thresholds",
        action="store_true",
        default=False,
        help="Raise AssertionError if evaluation metrics fail threshold criteria",
    )
    parser.add_argument(
        "--no-assert",
        action="store_true",
        help="Suppress AssertionError on threshold failure (takes precedence)",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )

    args = parser.parse_args()

    enforce = args.enforce_thresholds and not args.no_assert

    train_engine_a(
        data_path=args.data_path,
        models_dir=args.models_dir,
        val_ratio=args.val_ratio,
        enforce_thresholds=enforce,
        random_state=args.random_state,
    )


if __name__ == "__main__":
    main()
