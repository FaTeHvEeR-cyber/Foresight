"""Engine B Anomaly Detection Training Pipeline.

Trains an unsupervised Isolation Forest model on benchmark feature data,
evaluates predictions against held-out ground truth anomaly labels,
verifies strict performance criteria (Recall >= 90% and [Precision >= 80% or F1 >= 0.85]),
and serializes the trained model to models/isolation_forest.joblib.
"""

import argparse
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, IsolationForest
from sklearn.metrics import f1_score, precision_score, recall_score

logger = logging.getLogger("engine_b_anomaly")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def find_benchmark_file(filename: str, override_path: Optional[str] = None) -> Path:
    """Resolve file path across potential run locations (repo root, backend dir, CLI override)."""
    if override_path:
        p = Path(override_path)
        if p.exists():
            return p
        raise FileNotFoundError(f"Specified path not found: {override_path}")

    current_dir = Path.cwd()
    script_dir = Path(__file__).resolve().parent

    candidates = [
        current_dir / filename,
        current_dir / "data" / filename,
        current_dir / "backend" / "data" / filename,
        script_dir.parents[1] / "data" / filename,  # backend/data
        script_dir.parents[2] / "data" / filename,
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    candidates_str = "\n".join(str(c) for c in candidates)
    raise FileNotFoundError(
        f"Could not find {filename}. Checked candidates:\n{candidates_str}"
    )


def load_data(
    benchmark_path: Optional[str] = None,
    ground_truth_path: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Load benchmark feature data and held-out ground-truth validation labels.

    Ensures no label leakage by verifying that the feature dataset does not
    contain the ground-truth anomaly indicator column.
    """
    feat_file = find_benchmark_file("benchmark_data.parquet", benchmark_path)
    gt_file = find_benchmark_file("benchmark_data_ground_truth.parquet", ground_truth_path)

    logger.info("Loading feature dataset from: %s", feat_file)
    features_df = pd.read_parquet(feat_file)

    logger.info("Loading ground truth labels from: %s", gt_file)
    ground_truth_df = pd.read_parquet(gt_file)

    # Strict check to prevent label leakage
    if "is_anomaly" in features_df.columns:
        raise ValueError(
            "Data leakage detected! 'is_anomaly' found in feature dataset benchmark_data.parquet"
        )

    if "is_anomaly" not in ground_truth_df.columns:
        raise ValueError(
            "Ground truth file missing 'is_anomaly' column in benchmark_data_ground_truth.parquet"
        )

    labels = ground_truth_df["is_anomaly"].astype(bool)

    if len(features_df) != len(labels):
        raise ValueError(
            f"Row count mismatch between features ({len(features_df)}) and labels ({len(labels)})"
        )

    logger.info(
        "Successfully loaded %d records. Ground-truth anomalies: %d (%.2f%%)",
        len(features_df),
        labels.sum(),
        (labels.sum() / len(features_df)) * 100,
    )
    return features_df, pd.Series(labels)


def prepare_anomaly_features(
    df: pd.DataFrame,
    regressor: Optional[HistGradientBoostingRegressor] = None,
    fit_regressor: bool = True,
) -> Tuple[pd.DataFrame, HistGradientBoostingRegressor]:
    """Unsupervised feature preparation for Isolation Forest.

    Contextual anomalies (such as sales drops during high-volume store hours)
    require comparing observed volume against expected baseline volume.
    An unsupervised regressor learns E[units_sold | context] from features only,
    producing contextual residuals without using ground truth labels.
    """
    context_columns = [
        "store_type",
        "promo_flag",
        "day_of_week",
        "local_holiday",
        "temperature",
        "competitor_distance",
        "inventory_level",
        "customer_rating",
        "region",
    ]

    available_cols = [c for c in context_columns if c in df.columns]
    X_context = pd.get_dummies(df[available_cols], drop_first=True)

    if fit_regressor or regressor is None:
        regressor = HistGradientBoostingRegressor(random_state=42, max_iter=100)
        regressor.fit(X_context, df["units_sold"])

    expected_units = regressor.predict(X_context)

    # Compute contextual residuals and temperature outlier signal
    sales_residual = df["units_sold"] - expected_units
    sales_log_ratio = np.log((df["units_sold"] + 1.0) / (np.maximum(expected_units, 1.0) + 1.0))
    temperature = df["temperature"]

    features = pd.DataFrame(
        {
            "sales_residual": sales_residual,
            "sales_log_ratio": sales_log_ratio,
            "temperature": temperature,
        },
        index=df.index,
    )

    return features, regressor


def fit_isolation_forest(
    features: pd.DataFrame,
    contamination: float = 0.052,
    random_state: int = 42,
    n_estimators: int = 300,
) -> IsolationForest:
    """Fit Isolation Forest model with contamination calibrated to ~5% on feature data.

    Fitting is strictly unsupervised and does not use ground truth labels.
    """
    logger.info(
        "Fitting Isolation Forest on %d samples with contamination=%.4f, n_estimators=%d",
        len(features),
        contamination,
        n_estimators,
    )
    iso = IsolationForest(
        contamination=contamination,  # type: ignore[arg-type]
        random_state=random_state,
        n_estimators=n_estimators,
        n_jobs=-1,
    )
    iso.fit(features)
    return iso


def evaluate_predictions(
    model: IsolationForest,
    features: pd.DataFrame,
    ground_truth: pd.Series,
) -> Dict[str, float]:
    """Evaluate Isolation Forest predictions against held-out ground truth.

    Computes and prints Recall, Precision, and F1 score regardless of pass/fail.
    Asserts Recall >= 90% AND (Precision >= 80% OR F1 >= 0.85).
    """
    # IsolationForest returns -1 for outliers (anomalies) and +1 for inliers (normal)
    raw_predictions = model.predict(features)
    predicted_anomalies = raw_predictions == -1

    recall = float(recall_score(ground_truth, predicted_anomalies))
    precision = float(precision_score(ground_truth, predicted_anomalies))
    f1 = float(f1_score(ground_truth, predicted_anomalies))

    metrics = {
        "recall": recall,
        "precision": precision,
        "f1": f1,
        "true_positives": int(np.sum(ground_truth & predicted_anomalies)),
        "false_positives": int(np.sum((~ground_truth) & predicted_anomalies)),
        "false_negatives": int(np.sum(ground_truth & (~predicted_anomalies))),
        "true_negatives": int(np.sum((~ground_truth) & (~predicted_anomalies))),
    }

    # Print report regardless of pass/fail
    print("\n" + "=" * 60, flush=True)
    print("Engine B Isolation Forest Anomaly Detection Evaluation Metrics:", flush=True)
    print("=" * 60, flush=True)
    print(f"  Recall:    {recall:.4f} ({recall * 100:.2f}%)  [Target: >= 90.0%]", flush=True)
    print(f"  Precision: {precision:.4f} ({precision * 100:.2f}%)  [Target: >= 80.0% (or F1 >= 0.85)]", flush=True)
    print(f"  F1 Score:  {f1:.4f}          [Target: >= 0.85 (or Precision >= 80.0%)]", flush=True)
    print(f"  True Positives:  {metrics['true_positives']}", flush=True)
    print(f"  False Positives: {metrics['false_positives']}", flush=True)
    print(f"  False Negatives: {metrics['false_negatives']}", flush=True)
    print(f"  True Negatives:  {metrics['true_negatives']}", flush=True)
    print("=" * 60 + "\n", flush=True)

    # Assert performance criteria: Recall >= 90% AND (Precision >= 80% OR F1 >= 0.85)
    assert recall >= 0.90, (
        f"Assertion Failed: Recall {recall:.4f} is below required threshold of 0.90"
    )
    assert precision >= 0.80 or f1 >= 0.85, (
        f"Assertion Failed: Precision {precision:.4f} is below 0.80 AND F1 {f1:.4f} is below 0.85"
    )

    print("All evaluation assertions PASSED successfully!", flush=True)
    return metrics


def resolve_output_path(output_path: Optional[str] = None) -> Path:
    """Determine target output path for serialized isolation forest model."""
    if output_path:
        return Path(output_path)

    # Default to models/isolation_forest.joblib
    return Path("models") / "isolation_forest.joblib"


def serialize_model(
    model: IsolationForest,
    regressor: Optional[HistGradientBoostingRegressor] = None,
    output_path: Optional[str] = None,
) -> Path:
    """Serialize the trained IsolationForest model and optional preprocessor to disk."""
    dest = resolve_output_path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, dest)
    logger.info("Serialized Isolation Forest model to: %s", dest.resolve())

    if regressor is not None:
        preprocessor_dest = dest.parent / "isolation_forest_preprocessor.joblib"
        joblib.dump(regressor, preprocessor_dest)
        logger.info("Serialized contextual feature preprocessor to: %s", preprocessor_dest.resolve())

    # If running from backend or repo root, also mirror to backend/models or root models if different
    try:
        abs_dest = dest.resolve()
        # If dest is in Foresight/models, mirror to Foresight/backend/models
        if "backend" not in abs_dest.parts:
            backend_mirror = abs_dest.parents[1] / "backend" / "models" / abs_dest.name
            backend_mirror.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(model, backend_mirror)
            if regressor is not None:
                joblib.dump(regressor, backend_mirror.parent / "isolation_forest_preprocessor.joblib")
            logger.info("Mirrored model to backend directory: %s", backend_mirror)
        else:
            # If dest is in Foresight/backend/models, mirror to Foresight/models
            root_mirror = abs_dest.parents[2] / "models" / abs_dest.name
            root_mirror.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(model, root_mirror)
            if regressor is not None:
                joblib.dump(regressor, root_mirror.parent / "isolation_forest_preprocessor.joblib")
            logger.info("Mirrored model to root directory: %s", root_mirror)
    except Exception as e:
        logger.debug("Could not create mirror copy: %s", e)

    return dest


def train_pipeline(
    benchmark_path: Optional[str] = None,
    ground_truth_path: Optional[str] = None,
    output_path: Optional[str] = None,
    contamination: float = 0.052,
    random_state: int = 42,
) -> Tuple[IsolationForest, Dict[str, float]]:
    """Execute complete training, evaluation, and serialization pipeline."""
    # 1. Load benchmark data (features) and ground truth (validation-only)
    features_df, ground_truth = load_data(benchmark_path, ground_truth_path)

    # 2. Extract unsupervised contextual features
    features, regressor = prepare_anomaly_features(features_df, fit_regressor=True)

    # 3. Fit Isolation Forest with contamination calibrated to ~5%
    model = fit_isolation_forest(
        features=features,
        contamination=contamination,
        random_state=random_state,
    )

    # 4. Evaluate against held-out ground truth and assert thresholds
    metrics = evaluate_predictions(model, features, ground_truth)

    # 5. Serialize model to models/isolation_forest.joblib
    serialize_model(model, regressor=regressor, output_path=output_path)

    return model, metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Train Engine B Isolation Forest anomaly detector on benchmark data."
    )
    parser.add_argument(
        "--benchmark-data",
        type=str,
        default=None,
        help="Path to benchmark_data.parquet (default: auto-detected)",
    )
    parser.add_argument(
        "--ground-truth",
        type=str,
        default=None,
        help="Path to benchmark_data_ground_truth.parquet (default: auto-detected)",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default="models/isolation_forest.joblib",
        help="Target output path for serialized model (default: models/isolation_forest.joblib)",
    )
    parser.add_argument(
        "--contamination",
        type=float,
        default=0.052,
        help="Calibrated contamination rate (default: 0.052 (~5%%))",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )

    args = parser.parse_args()

    train_pipeline(
        benchmark_path=args.benchmark_data,
        ground_truth_path=args.ground_truth,
        output_path=args.output_path,
        contamination=args.contamination,
        random_state=args.random_state,
    )
