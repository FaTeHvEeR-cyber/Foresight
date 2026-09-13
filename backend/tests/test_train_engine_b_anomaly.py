"""Unit tests for Engine B Isolation Forest anomaly detection training pipeline.

Verifies:
1. Data loading and strict prevention of ground-truth label leakage.
2. Unsupervised contextual feature preparation.
3. Isolation Forest model fitting with ~5% contamination calibration.
4. Performance criteria assertions: Recall >= 90% and (Precision >= 80% or F1 >= 0.85).
5. Model serialization to models/isolation_forest.joblib and deserialization inference.
"""

import subprocess
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import IsolationForest

from src.training.train_engine_b_anomaly import (
    evaluate_predictions,
    find_benchmark_file,
    fit_isolation_forest,
    load_data,
    prepare_anomaly_features,
    serialize_model,
    train_pipeline,
)


def test_find_benchmark_file():
    """Verify benchmark data files can be resolved reliably."""
    feat_path = find_benchmark_file("benchmark_data.parquet")
    gt_path = find_benchmark_file("benchmark_data_ground_truth.parquet")
    assert feat_path.exists()
    assert gt_path.exists()


def test_load_data_strict_no_leakage():
    """Verify that features and labels are loaded without label leakage."""
    features_df, labels = load_data()

    assert len(features_df) == len(labels)
    assert len(features_df) >= 5000
    assert "is_anomaly" not in features_df.columns, "Label leakage: 'is_anomaly' must NOT be in features!"
    assert labels.dtype == bool
    assert labels.sum() == int(len(features_df) * 0.05)  # Exactly 5.0% contamination


def test_prepare_anomaly_features():
    """Verify unsupervised contextual feature extraction produces expected signals."""
    features_df, _ = load_data()
    features, regressor = prepare_anomaly_features(features_df, fit_regressor=True)

    expected_cols = {"sales_residual", "sales_log_ratio", "temperature"}
    assert set(features.columns) == expected_cols
    assert len(features) == len(features_df)
    assert not features.isnull().any().any(), "Features must not contain null values."
    assert np.all(np.isfinite(features.values)), "Features must be finite numeric values."


def test_training_pipeline_and_performance_criteria():
    """Verify that the model meets Recall >= 90% and (Precision >= 80% or F1 >= 0.85)."""
    model, metrics = train_pipeline(contamination=0.052, random_state=42)

    assert isinstance(model, IsolationForest)
    assert "recall" in metrics
    assert "precision" in metrics
    assert "f1" in metrics

    recall = metrics["recall"]
    precision = metrics["precision"]
    f1 = metrics["f1"]

    assert recall >= 0.90, f"Recall {recall:.4f} did not meet required threshold >= 0.90"
    assert (
        precision >= 0.80 or f1 >= 0.85
    ), f"Neither Precision ({precision:.4f} >= 0.80) nor F1 ({f1:.4f} >= 0.85) was satisfied"


def test_model_serialization_and_inference(tmp_path):
    """Verify model serialization to joblib and deserialization inference."""
    features_df, labels = load_data()
    features, regressor = prepare_anomaly_features(features_df, fit_regressor=True)
    model = fit_isolation_forest(features, contamination=0.052, random_state=42)

    target_file = tmp_path / "models" / "isolation_forest.joblib"
    serialize_model(model, regressor=regressor, output_path=str(target_file))

    assert target_file.exists()
    loaded_model = joblib.load(target_file)
    assert isinstance(loaded_model, IsolationForest)

    preds = loaded_model.predict(features.iloc[:50])
    assert len(preds) == 50
    assert set(preds).issubset({-1, 1})


def test_cli_execution():
    """Verify that running the script as CLI executes successfully with exit code 0."""
    script_path = Path(__file__).resolve().parents[1] / "src" / "training" / "train_engine_b_anomaly.py"
    backend_dir = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"CLI execution failed with error:\n{result.stderr}\n{result.stdout}"
    assert "Engine B Isolation Forest Anomaly Detection Evaluation Metrics:" in result.stdout
    assert "All evaluation assertions PASSED successfully!" in result.stdout
