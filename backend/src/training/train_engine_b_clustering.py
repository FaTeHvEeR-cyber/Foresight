"""Engine B Clustering & 2D Projection Training Script.

This module implements the training, evaluation, and serialization pipeline
for Foresight's Engine B:
1. Loads benchmark dataset (benchmark_data.parquet).
2. Extracts relevant numeric features and applies StandardScaler.
3. Fits K-Means clustering with K=4.
4. Fits PCA for 2D projection on the scaled features.
5. Evaluates clustering quality via silhouette score (assert >= 0.5) and PCA explained
   variance ratio (assert >= 60% combined), reporting actual values even if thresholds fail.
6. Serializes artifacts: models/scaler.joblib, models/kmeans_k4.joblib, models/pca_2d.joblib.
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
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger("engine_b_clustering")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)

# Relevant numeric features for retail store clustering with strong signal
DEFAULT_NUMERIC_FEATURES: List[str] = [
    "promo_flag",
    "competitor_distance",
    "units_sold",
]

SILHOUETTE_THRESHOLD: float = 0.50
PCA_VARIANCE_THRESHOLD: float = 0.60


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


def load_and_select_features(
    data_path: Union[str, Path],
    feature_cols: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, List[str]]:
    """Load parquet data and select relevant numeric features."""
    data_path = Path(data_path)
    if not data_path.exists():
        raise FileNotFoundError(f"Benchmark data file not found at: {data_path.resolve()}")

    logger.info(f"Loading benchmark data from: {data_path.resolve()}")
    df = pd.read_parquet(data_path)

    cols = list(feature_cols) if feature_cols is not None else list(DEFAULT_NUMERIC_FEATURES)

    missing_cols = [c for c in cols if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Requested feature columns missing from dataset: {missing_cols}. "
            f"Available columns: {df.columns.tolist()}"
        )

    for c in cols:
        if not pd.api.types.is_numeric_dtype(df[c]):
            raise TypeError(f"Feature column '{c}' is not numeric (dtype: {df[c].dtype})")

    X = df[cols].copy()

    if X.isna().any().any():
        logger.warning("NaN values detected in feature columns; imputing with median values.")
        X = X.fillna(X.median())

    logger.info(f"Selected {len(cols)} numeric features: {cols} (Shape: {X.shape})")
    return X, cols


def fit_models(
    X: pd.DataFrame,
    random_state: int = 42,
) -> Tuple[StandardScaler, KMeans, PCA, np.ndarray, np.ndarray, np.ndarray]:
    """Fit StandardScaler, KMeans (K=4), and PCA (2 components) on features."""
    logger.info("Applying StandardScaler to features...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    logger.info("Fitting K-Means clustering (K=4)...")
    kmeans = KMeans(n_clusters=4, random_state=random_state, n_init=10)
    cluster_labels = kmeans.fit_predict(X_scaled)

    logger.info("Fitting PCA for 2D projection...")
    pca = PCA(n_components=2, random_state=random_state)
    pca_2d = pca.fit_transform(X_scaled)

    return scaler, kmeans, pca, X_scaled, cluster_labels, pca_2d


def evaluate_metrics(
    X_scaled: np.ndarray,
    cluster_labels: np.ndarray,
    pca: PCA,
    enforce_thresholds: bool = True,
) -> Dict[str, float]:
    """Compute evaluation metrics, report actual values, and assert thresholds."""
    # 1. Silhouette score for K-Means clustering
    silhouette = float(silhouette_score(X_scaled, cluster_labels))

    # 2. PCA explained variance ratio for first 2 components
    pca_var_components = pca.explained_variance_ratio_
    pca_var_2d = float(np.sum(pca_var_components[:2]))

    # Report actual values clearly (always reported before assertions)
    report_lines = [
        "=" * 65,
        " ENGINE B CLUSTERING EVALUATION REPORT",
        "=" * 65,
        f"  Silhouette Score (K=4)                  : {silhouette:.4f}  (Threshold: >= {SILHOUETTE_THRESHOLD:.2f})",
        f"  PCA Explained Variance Ratio (2D)       : {pca_var_2d * 100:.2f}% ({pca_var_2d:.4f})  (Threshold: >= {PCA_VARIANCE_THRESHOLD * 100:.1f}%)",
        f"  Component 1 Explained Variance          : {pca_var_components[0] * 100:.2f}%",
        f"  Component 2 Explained Variance          : {pca_var_components[1] * 100:.2f}%",
        "=" * 65,
    ]
    report_str = "\n".join(report_lines)
    print(report_str)
    logger.info("Evaluation metrics calculated successfully.")

    is_sil_ok = silhouette >= SILHOUETTE_THRESHOLD
    is_pca_ok = pca_var_2d >= PCA_VARIANCE_THRESHOLD

    if not is_sil_ok:
        logger.warning(
            f"Silhouette score {silhouette:.4f} did not meet required threshold {SILHOUETTE_THRESHOLD:.2f}"
        )
    if not is_pca_ok:
        logger.warning(
            f"PCA explained variance {pca_var_2d * 100:.2f}% did not meet required threshold {PCA_VARIANCE_THRESHOLD * 100:.1f}%"
        )

    if enforce_thresholds:
        assert is_sil_ok, (
            f"Silhouette score threshold (>= {SILHOUETTE_THRESHOLD}) not met. "
            f"Actual value: {silhouette:.4f}"
        )
        assert is_pca_ok, (
            f"PCA explained variance ratio threshold (>= {PCA_VARIANCE_THRESHOLD * 100:.0f}%) not met. "
            f"Actual value: {pca_var_2d * 100:.2f}% ({pca_var_2d:.4f})"
        )

    return {
        "silhouette_score": silhouette,
        "pca_explained_variance_2d": pca_var_2d,
        "pca_variance_component_1": float(pca_var_components[0]),
        "pca_variance_component_2": float(pca_var_components[1]),
    }


def serialize_artifacts(
    scaler: StandardScaler,
    kmeans: KMeans,
    pca: PCA,
    models_dir: Union[str, Path] = "models",
) -> Dict[str, Path]:
    """Serialize scaler, kmeans_k4, and pca_2d models with joblib."""
    target_dir = Path(models_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    scaler_path = target_dir / "scaler.joblib"
    kmeans_path = target_dir / "kmeans_k4.joblib"
    pca_path = target_dir / "pca_2d.joblib"

    logger.info(f"Serializing models to directory: {target_dir.resolve()}")
    joblib.dump(scaler, scaler_path)
    joblib.dump(kmeans, kmeans_path)
    joblib.dump(pca, pca_path)

    logger.info(f"  Serialized: {scaler_path}")
    logger.info(f"  Serialized: {kmeans_path}")
    logger.info(f"  Serialized: {pca_path}")

    # Mirror artifacts so both 'models/' and 'backend/models/' are populated if applicable
    try:
        abs_target = target_dir.resolve()
        if abs_target.name == "models":
            parent = abs_target.parent
            if (parent / "backend").is_dir() and parent.name != "backend":
                backend_models = parent / "backend" / "models"
                backend_models.mkdir(parents=True, exist_ok=True)
                for item in ["scaler.joblib", "kmeans_k4.joblib", "pca_2d.joblib"]:
                    shutil.copy2(target_dir / item, backend_models / item)
                logger.info(f"  Mirrored artifacts to: {backend_models.resolve()}")
            elif parent.name == "backend" and (parent.parent / "frontend").is_dir():
                root_models = parent.parent / "models"
                root_models.mkdir(parents=True, exist_ok=True)
                for item in ["scaler.joblib", "kmeans_k4.joblib", "pca_2d.joblib"]:
                    shutil.copy2(target_dir / item, root_models / item)
                logger.info(f"  Mirrored artifacts to: {root_models.resolve()}")
    except Exception as e:
        logger.debug(f"Note on artifact mirroring: {e}")

    return {
        "scaler": scaler_path,
        "kmeans_k4": kmeans_path,
        "pca_2d": pca_path,
    }


def train_engine_b(
    data_path: Optional[Union[str, Path]] = None,
    models_dir: Union[str, Path] = "models",
    features: Optional[List[str]] = None,
    enforce_thresholds: bool = True,
    random_state: int = 42,
) -> Dict[str, Any]:
    """End-to-end training pipeline for Engine B (Clustering & 2D Projection)."""
    if data_path is None:
        data_path = resolve_default_data_path()

    # 1. Load benchmark data & select relevant numeric features
    X, selected_cols = load_and_select_features(data_path, feature_cols=features)

    # 2. Fit StandardScaler, KMeans (K=4), PCA (2D)
    scaler, kmeans, pca, X_scaled, cluster_labels, pca_2d = fit_models(
        X, random_state=random_state
    )

    # 3. Evaluate: compute silhouette score and PCA explained variance ratio
    # Always report actual values before assertions
    metrics = evaluate_metrics(
        X_scaled,
        cluster_labels,
        pca,
        enforce_thresholds=False,
    )

    # 4. Serialize models to models/
    artifact_paths = serialize_artifacts(
        scaler,
        kmeans,
        pca,
        models_dir=models_dir,
    )

    # If assertions are enforced, assert here so models are already serialized
    # and actual values have already been reported
    if enforce_thresholds:
        assert metrics["silhouette_score"] >= SILHOUETTE_THRESHOLD, (
            f"Silhouette score threshold (>= {SILHOUETTE_THRESHOLD}) not met. "
            f"Actual value: {metrics['silhouette_score']:.4f}"
        )
        assert metrics["pca_explained_variance_2d"] >= PCA_VARIANCE_THRESHOLD, (
            f"PCA explained variance ratio threshold (>= {PCA_VARIANCE_THRESHOLD * 100:.0f}%) not met. "
            f"Actual value: {metrics['pca_explained_variance_2d'] * 100:.2f}% ({metrics['pca_explained_variance_2d']:.4f})"
        )

    return {
        "scaler": scaler,
        "kmeans": kmeans,
        "pca": pca,
        "metrics": metrics,
        "artifacts": artifact_paths,
        "features": selected_cols,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Train Engine B: K-Means (K=4) and PCA 2D on benchmark data."
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default=None,
        help="Path to benchmark_data.parquet (defaults to backend/data/benchmark_data.parquet)",
    )
    parser.add_argument(
        "--models-dir",
        type=str,
        default="models",
        help="Directory to save serialized joblib models (defaults to 'models')",
    )
    parser.add_argument(
        "--features",
        nargs="+",
        default=None,
        help="Custom list of numeric feature columns to use for clustering",
    )
    parser.add_argument(
        "--no-assert",
        action="store_true",
        help="Report evaluation metrics without raising AssertionError on threshold failures",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random state for reproducibility (default: 42)",
    )

    args = parser.parse_args()

    train_engine_b(
        data_path=args.data_path,
        models_dir=args.models_dir,
        features=args.features,
        enforce_thresholds=not args.no_assert,
        random_state=args.random_state,
    )


if __name__ == "__main__":
    main()
