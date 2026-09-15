"""Tests for Engine B Clustering training pipeline (train_engine_b_clustering.py)."""

from pathlib import Path
import joblib
import pytest
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from src.training.train_engine_b_clustering import (
    SILHOUETTE_THRESHOLD,
    PCA_VARIANCE_THRESHOLD,
    train_engine_b,
)


def test_engine_b_training_end_to_end(tmp_path):
    """Verify Engine B training satisfies all thresholds and serializes artifacts."""
    output_dir = tmp_path / "models"
    result = train_engine_b(
        models_dir=output_dir,
        enforce_thresholds=True,
        random_state=42,
    )

    # 1. Returned structure
    assert "scaler" in result
    assert "kmeans" in result
    assert "pca" in result
    assert "metrics" in result
    assert "artifacts" in result
    assert "features" in result

    # 2. Fitted models
    assert isinstance(result["scaler"], StandardScaler)
    assert isinstance(result["kmeans"], KMeans)
    assert isinstance(result["pca"], PCA)
    assert result["kmeans"].n_clusters == 4
    assert result["pca"].n_components == 2

    # 3. Metrics thresholds
    metrics = result["metrics"]
    assert metrics["silhouette_score"] >= SILHOUETTE_THRESHOLD, (
        f"Expected silhouette >= {SILHOUETTE_THRESHOLD}, got {metrics['silhouette_score']}"
    )
    assert metrics["pca_explained_variance_2d"] >= PCA_VARIANCE_THRESHOLD, (
        f"Expected PCA variance >= {PCA_VARIANCE_THRESHOLD}, got {metrics['pca_explained_variance_2d']}"
    )

    # 4. Serialized artifacts exist and deserialize accurately
    scaler_path = Path(result["artifacts"]["scaler"])
    kmeans_path = Path(result["artifacts"]["kmeans_k4"])
    pca_path = Path(result["artifacts"]["pca_2d"])

    assert scaler_path.is_file()
    assert kmeans_path.is_file()
    assert pca_path.is_file()

    loaded_scaler = joblib.load(scaler_path)
    loaded_kmeans = joblib.load(kmeans_path)
    loaded_pca = joblib.load(pca_path)

    assert isinstance(loaded_scaler, StandardScaler)
    assert isinstance(loaded_kmeans, KMeans)
    assert isinstance(loaded_pca, PCA)
    assert loaded_kmeans.n_clusters == 4
    assert loaded_pca.n_components == 2


def test_engine_b_custom_features_and_reporting(tmp_path):
    """Verify behavior when evaluating features that fail thresholds."""
    output_dir = tmp_path / "models"
    failing_features = [
        "day_of_week",
        "promo_flag",
        "temperature",
        "competitor_distance",
        "inventory_level",
        "customer_rating",
        "local_holiday",
        "units_sold",
    ]

    # Without assertion enforcement: reports actual values cleanly
    result = train_engine_b(
        models_dir=output_dir,
        features=failing_features,
        enforce_thresholds=False,
        random_state=42,
    )
    assert result["metrics"]["silhouette_score"] < SILHOUETTE_THRESHOLD
    assert result["metrics"]["pca_explained_variance_2d"] < PCA_VARIANCE_THRESHOLD

    # With assertion enforcement: raises AssertionError containing actual values
    with pytest.raises(AssertionError) as excinfo:
        train_engine_b(
            models_dir=output_dir,
            features=failing_features,
            enforce_thresholds=True,
            random_state=42,
        )
    assert "Silhouette score threshold" in str(excinfo.value)
    assert "Actual value" in str(excinfo.value)


def test_engine_b_nonexistent_data():
    """Verify FileNotFoundError on bad dataset path."""
    with pytest.raises(FileNotFoundError):
        train_engine_b(data_path="nonexistent_data.parquet")


def test_engine_b_invalid_feature():
    """Verify ValueError on nonexistent feature."""
    with pytest.raises(ValueError):
        train_engine_b(features=["non_existent_col"])
