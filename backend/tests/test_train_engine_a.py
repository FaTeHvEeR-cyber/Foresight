"""Tests for Engine A Forecasting training pipeline (train_engine_a.py)."""

from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from xgboost import XGBRegressor

from src.training.train_engine_a import (
    LAG_PERIODS,
    ROLLING_WINDOWS,
    RMSPE_THRESHOLD,
    R2_THRESHOLD,
    compute_rmspe,
    engineer_features,
    load_dataset,
    split_train_validation,
    train_engine_a,
    verify_thresholds,
)


def test_train_engine_a_end_to_end(tmp_path):
    """Verify Engine A training runs end-to-end, trains all three models, and serializes artifacts."""
    output_dir = tmp_path / "models"
    result = train_engine_a(
        models_dir=output_dir,
        enforce_thresholds=False,
        random_state=42,
    )

    # 1. Returned dictionary structure
    assert "models" in result
    assert "metrics" in result
    assert "artifacts" in result
    assert "feature_names" in result
    assert "scaler" in result
    assert "train_df" in result
    assert "val_df" in result

    # 2. Model types and fair training on identical feature sets
    models = result["models"]
    assert isinstance(models["ridge"], Ridge)
    assert isinstance(models["xgboost"], XGBRegressor)
    assert isinstance(models["mlp"], MLPRegressor)

    # 3. All metrics computed per model
    metrics = result["metrics"]
    for model_name in ["ridge", "xgboost", "mlp"]:
        assert model_name in metrics, f"Missing metrics for {model_name}"
        m = metrics[model_name]
        assert "rmspe" in m and isinstance(m["rmspe"], float) and np.isfinite(m["rmspe"])
        assert "mae" in m and isinstance(m["mae"], float) and np.isfinite(m["mae"])
        assert "rmse" in m and isinstance(m["rmse"], float) and np.isfinite(m["rmse"])
        assert "r2" in m and isinstance(m["r2"], float) and np.isfinite(m["r2"])

    # 4. XGBoost RMSPE must be lower (better) than Ridge's
    xgb_rmspe = metrics["xgboost"]["rmspe"]
    ridge_rmspe = metrics["ridge"]["rmspe"]
    assert xgb_rmspe < ridge_rmspe, (
        f"Expected XGBoost RMSPE ({xgb_rmspe:.2f}%) to be lower than Ridge RMSPE ({ridge_rmspe:.2f}%)"
    )

    # 5. Serialized artifacts exist and deserialize cleanly
    artifacts = result["artifacts"]
    assert Path(artifacts["ridge"]).is_file()
    assert Path(artifacts["xgboost"]).is_file()
    assert Path(artifacts["mlp"]).is_file()

    loaded_ridge = joblib.load(artifacts["ridge"])
    loaded_xgb = joblib.load(artifacts["xgboost"])
    loaded_mlp = joblib.load(artifacts["mlp"])

    assert isinstance(loaded_ridge, Ridge)
    assert isinstance(loaded_xgb, XGBRegressor)
    assert isinstance(loaded_mlp, MLPRegressor)


def test_train_engine_a_no_temporal_leakage():
    """Verify that lag and rolling features do not leak current or future target values."""
    # Create synthetic series
    dates = pd.date_range("2022-01-01", periods=40, freq="D")
    df = pd.DataFrame({
        "store_id": 1,
        "date": dates,
        "units_sold": np.arange(1, 41) * 10,  # 10, 20, 30, ...
        "day_of_week": dates.dayofweek,
        "promo_flag": 0,
        "temperature": 20.0,
        "competitor_distance": 5.0,
        "store_type": "Mall",
        "region": "North",
        "inventory_level": 500,
        "customer_rating": 4.0,
        "local_holiday": 0,
    })

    engineered = engineer_features(df)

    # For any row in engineered df:
    # 1. lag_7 must match the target value from 7 days ago
    for idx, row in engineered.iterrows():
        orig_row = df[df["date"] == row["date"]].iloc[0]
        curr_val = orig_row["units_sold"]

        date_t_minus_7 = row["date"] - pd.Timedelta(days=7)
        past_row = df[df["date"] == date_t_minus_7]
        if not past_row.empty:
            assert row["lag_7"] == past_row.iloc[0]["units_sold"]

        # 2. rolling_mean_7 must strictly use shift(1), so it must NOT include curr_val
        date_t_minus_1 = row["date"] - pd.Timedelta(days=1)
        window_7_dates = pd.date_range(end=date_t_minus_1, periods=7, freq="D")
        past_window_vals = df[df["date"].isin(window_7_dates)]["units_sold"]
        expected_rolling_mean = past_window_vals.mean()
        assert np.isclose(row["rolling_mean_7"], expected_rolling_mean)


def test_train_engine_a_split_strict_time_cutoff():
    """Verify time-based train/validation split enforces strict chronological order."""
    dates = pd.date_range("2022-01-01", periods=100, freq="D")
    df = pd.DataFrame({
        "store_id": np.repeat([1, 2], 50),
        "date": np.tile(dates[:50], 2),
        "units_sold": 100,
        "promo_flag": 0,
        "temperature": 18.0,
        "competitor_distance": 2.5,
        "store_type": "Street",
        "region": "West",
        "inventory_level": 300,
        "customer_rating": 4.2,
        "local_holiday": 0,
        "day_of_week": 1,
        "day_of_month": 1,
        "month": 1,
        "day_of_year": 1,
        "is_weekend": 0,
        "sin_dow": 0.0,
        "cos_dow": 1.0,
        "sin_month": 0.5,
        "cos_month": 0.86,
        "sin_doy": 0.1,
        "cos_doy": 0.99,
        "lag_7": 100,
        "lag_14": 100,
        "lag_21": 100,
        "lag_30": 100,
        "rolling_mean_7": 100,
        "rolling_std_7": 0,
        "rolling_mean_14": 100,
        "rolling_std_14": 0,
        "rolling_mean_30": 100,
        "rolling_std_30": 0,
    })

    X_train, X_val, y_train, y_val, scaler, feature_names, train_df, val_df = split_train_validation(
        df, val_ratio=0.20
    )

    max_train_date = train_df["date"].max()
    min_val_date = val_df["date"].max()
    assert max_train_date < val_df["date"].min(), (
        f"Train max date ({max_train_date}) must strictly precede val min date ({val_df['date'].min()})"
    )
    assert X_train.shape[1] == X_val.shape[1] == len(feature_names)


def test_train_engine_a_compute_rmspe():
    """Verify compute_rmspe calculation accuracy and zero-safe handling."""
    y_true = np.array([100.0, 200.0, 50.0])
    y_pred = np.array([110.0, 190.0, 55.0])
    # Relative errors: (100 - 110)/100 = -0.10; (200 - 190)/200 = 0.05; (50 - 55)/50 = -0.10
    # Squares: 0.01, 0.0025, 0.01 -> mean: 0.0225 / 3 = 0.0075
    # sqrt(0.0075) * 100% = 8.66025%
    expected = np.sqrt(np.mean([0.01, 0.0025, 0.01])) * 100.0
    actual = compute_rmspe(y_true, y_pred)
    assert np.isclose(actual, expected)

    # Empty / zeros handling
    assert compute_rmspe(np.array([0.0, 0.0]), np.array([10.0, 20.0])) == 0.0


def test_train_engine_a_threshold_assertions():
    """Verify verify_thresholds raises AssertionError on failure when enforced."""
    # Passing metrics mock
    passing_metrics = {
        "xgboost": {"rmspe": 12.0, "mae": 15.0, "rmse": 20.0, "r2": 0.88},
        "ridge": {"rmspe": 18.0, "mae": 22.0, "rmse": 28.0, "r2": 0.81},
        "mlp": {"rmspe": 20.0, "mae": 25.0, "rmse": 32.0, "r2": 0.79},
    }
    # Should not raise
    verify_thresholds(passing_metrics, enforce_thresholds=True)

    # Failing metrics mock (XGBoost RMSPE > Ridge RMSPE)
    failing_metrics = {
        "xgboost": {"rmspe": 25.0, "mae": 15.0, "rmse": 20.0, "r2": 0.80},
        "ridge": {"rmspe": 20.0, "mae": 22.0, "rmse": 28.0, "r2": 0.81},
        "mlp": {"rmspe": 30.0, "mae": 25.0, "rmse": 32.0, "r2": 0.75},
    }
    with pytest.raises(AssertionError) as excinfo:
        verify_thresholds(failing_metrics, enforce_thresholds=True)
    assert "Threshold Assertion Failed" in str(excinfo.value)

    # When enforce_thresholds=False, should NOT raise even if failing
    verify_thresholds(failing_metrics, enforce_thresholds=False)


def test_train_engine_a_missing_data():
    """Verify FileNotFoundError on non-existent dataset path."""
    with pytest.raises(FileNotFoundError):
        train_engine_a(data_path="nonexistent_dataset.parquet")


def test_train_engine_a_ground_truth_exclusion(tmp_path):
    """Verify that validation anomalies are identified, excluded from evaluation, and reported."""
    output_dir = tmp_path / "models"
    result = train_engine_a(
        models_dir=output_dir,
        enforce_thresholds=False,
        random_state=42,
    )

    assert "exclusion_stats" in result
    stats = result["exclusion_stats"]

    # Check structure and values of exclusion_stats
    assert stats["total_val_rows"] == 900
    assert stats["excluded_rows"] == 48
    assert stats["clean_val_rows"] == 852
    assert np.isclose(stats["excluded_pct"], 5.333333333, atol=0.01)

    # Verify that training data retained full messy data (including anomalies)
    train_df = result["train_df"]
    assert len(train_df) == 3600
    gt_path = Path(__file__).resolve().parent.parent / "data" / "benchmark_data_ground_truth.parquet"
    if gt_path.is_file():
        gt_df = pd.read_parquet(gt_path)
        gt_anomalies = set(gt_df[gt_df["is_anomaly"]]["row_index"])
        train_anomalies = set(train_df["row_index"]).intersection(gt_anomalies)
        # Training set MUST retain anomalous rows
        assert len(train_anomalies) > 0, "Training set should retain realistic messy anomalous rows!"
        assert len(train_anomalies) == 181  # 181 anomalies in retained training fold rows

    # Check metrics were computed and XGBoost outperforms Ridge
    metrics = result["metrics"]
    assert metrics["xgboost"]["rmspe"] < metrics["ridge"]["rmspe"]


def test_train_engine_a_missing_or_invalid_ground_truth(tmp_path):
    """Verify graceful fallback when ground truth is missing or missing expected columns."""
    output_dir = tmp_path / "models"

    # 1. Non-existent ground truth file -> evaluates all validation rows without crashing
    res_missing = train_engine_a(
        models_dir=output_dir / "missing",
        ground_truth_path="nonexistent_ground_truth.parquet",
        enforce_thresholds=False,
    )
    assert res_missing["exclusion_stats"]["excluded_rows"] == 0
    assert res_missing["exclusion_stats"]["clean_val_rows"] == res_missing["exclusion_stats"]["total_val_rows"]

    # 2. Corrupt/missing columns ground truth file
    bad_gt_file = tmp_path / "bad_gt.parquet"
    pd.DataFrame({"wrong_col": [1, 2, 3]}).to_parquet(bad_gt_file)
    res_bad = train_engine_a(
        models_dir=output_dir / "bad",
        ground_truth_path=bad_gt_file,
        enforce_thresholds=False,
    )
    assert res_bad["exclusion_stats"]["excluded_rows"] == 0
    assert res_bad["exclusion_stats"]["clean_val_rows"] == res_bad["exclusion_stats"]["total_val_rows"]


def test_train_engine_a_cli_execution(tmp_path):
    """Verify train_engine_a executes from CLI with transparency reporting output."""
    import subprocess
    import sys

    backend_dir = Path(__file__).resolve().parent.parent
    cmd = [
        sys.executable,
        "-m",
        "src.training.train_engine_a",
        "--models-dir",
        str(tmp_path / "models"),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"CLI execution failed:\nStdout: {proc.stdout}\nStderr: {proc.stderr}"
    assert "Validation Scope & Anomaly Exclusion:" in proc.stdout
    assert "Total validation rows   : 900" in proc.stdout
    assert "Excluded anomalous rows : 48 (5.33%)" in proc.stdout
    assert "Clean rows evaluated    : 852" in proc.stdout
    assert "FORESIGHT ENGINE A FORECASTING MODEL BENCHMARK SUMMARY" in proc.stdout

