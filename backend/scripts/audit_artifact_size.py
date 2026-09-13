"""Artifact Footprint Audit Script.

Audits serialized model artifacts produced by Foresight's training pipelines:
1. train_engine_a.py (Forecasting: Ridge, XGBoost, MLP, Scaler, Feature Schema)
2. train_engine_b_anomaly.py (Anomaly Detection: Isolation Forest, Contextual Preprocessor)
3. train_engine_b_clustering.py (Clustering: K-Means, PCA, Scaler)

Enforces architecture specification §5.2 ("artifact footprint"):
The total combined size of all serialized .joblib artifacts must stay strictly
under the 50MB ceiling.
Fails loudly with the exact overage amount if exceeded and flags the largest
contributor(s) to optimize first.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Architecture spec §5.2 default ceiling: 50MB (binary MiB: 50 * 1024 * 1024 bytes)
DEFAULT_CEILING_MB: float = 50.0
BYTES_PER_MB: int = 1024 * 1024

# Mapping of known model artifacts to their producing pipeline scripts
KNOWN_MODEL_PRODUCERS: Dict[str, str] = {
    # Engine A: Forecasting pipeline
    "ridge_baseline.joblib": "train_engine_a.py (Ridge Baseline)",
    "xgboost_primary.joblib": "train_engine_a.py (XGBoost Primary)",
    "mlp_benchmark.joblib": "train_engine_a.py (MLP Benchmark)",
    "engine_a_scaler.joblib": "train_engine_a.py (Forecasting Scaler)",
    "engine_a_features.joblib": "train_engine_a.py (Feature Schema)",
    # Engine B: Anomaly Detection pipeline
    "isolation_forest.joblib": "train_engine_b_anomaly.py (Isolation Forest)",
    "isolation_forest_preprocessor.joblib": "train_engine_b_anomaly.py (Contextual Regressor)",
    # Engine B: Clustering & 2D Projection pipeline
    "kmeans_k4.joblib": "train_engine_b_clustering.py (K-Means Clustering)",
    "pca_2d.joblib": "train_engine_b_clustering.py (PCA 2D Projection)",
    "scaler.joblib": "train_engine_b_clustering.py (Clustering Scaler)",
}


def format_bytes(num_bytes: int) -> str:
    """Format bytes into human-readable string with units."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.2f} KB ({num_bytes:,} bytes)"
    elif num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.2f} MB ({num_bytes:,} bytes)"
    else:
        return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB ({num_bytes:,} bytes)"


def resolve_models_directory(custom_path: Optional[Union[str, Path]] = None) -> Path:
    """Locate the models directory across potential working locations."""
    if custom_path:
        p = Path(custom_path).resolve()
        if p.exists() and p.is_dir():
            return p
        raise FileNotFoundError(f"Specified models directory does not exist: {custom_path}")

    # Standard candidate locations
    candidates = [
        Path(__file__).resolve().parent.parent / "models",          # backend/models
        Path(__file__).resolve().parent.parent.parent / "models",   # repo_root/models
        Path.cwd() / "backend" / "models",                          # cwd/backend/models
        Path.cwd() / "models",                                      # cwd/models
    ]

    for candidate in candidates:
        if candidate.is_dir() and any(candidate.glob("*.joblib")):
            return candidate.resolve()

    # Fallback to first existing directory
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()

    raise FileNotFoundError(
        "Could not automatically locate 'models/' directory containing .joblib files. "
        "Please provide --models-dir explicitly."
    )


def audit_artifact_sizes(
    models_dir: Optional[Union[str, Path]] = None,
    ceiling_mb: float = DEFAULT_CEILING_MB,
    enforce_assertion: bool = True,
) -> Dict[str, Any]:
    """Audit all .joblib files in the models directory and check size ceiling.

    Args:
        models_dir: Path to models directory. If None, auto-resolves.
        ceiling_mb: Maximum total size limit in MB (default: 50.0 MB).
        enforce_assertion: If True, raises AssertionError on limit breach.

    Returns:
        Dictionary with audit summary and details per artifact.

    Raises:
        AssertionError: If total size exceeds ceiling and enforce_assertion=True.
        FileNotFoundError: If models directory does not exist.
    """
    target_dir = resolve_models_directory(models_dir)
    joblib_files = sorted(list(target_dir.glob("*.joblib")), key=lambda p: p.stat().st_size, reverse=True)

    if not joblib_files:
        print(f"[WARNING] No .joblib files found in models directory: {target_dir}")

    total_bytes = sum(f.stat().st_size for f in joblib_files)
    total_mb = total_bytes / BYTES_PER_MB
    ceiling_bytes = int(ceiling_mb * BYTES_PER_MB)
    overage_bytes = max(0, total_bytes - ceiling_bytes)
    overage_mb = max(0.0, total_mb - ceiling_mb)
    is_within_limit = total_bytes <= ceiling_bytes

    # Build per-file stats
    file_records = []
    for f in joblib_files:
        size = f.stat().st_size
        pct = (size / total_bytes * 100.0) if total_bytes > 0 else 0.0
        producer = KNOWN_MODEL_PRODUCERS.get(f.name, "Other / Custom Model")
        file_records.append({
            "name": f.name,
            "path": str(f),
            "size_bytes": size,
            "size_mb": size / BYTES_PER_MB,
            "size_formatted": format_bytes(size),
            "percentage_of_total": pct,
            "producer": producer,
        })

    # Display clean formatted audit table
    banner_width = 86
    print("=" * banner_width)
    print(" FORESIGHT ARTIFACT FOOTPRINT AUDIT (Section 5.2)")
    print("=" * banner_width)
    print(f"Scanned Directory: {target_dir}")
    print(f"Artifact Count:    {len(file_records)} .joblib file(s)")
    print(f"Size Ceiling:      {ceiling_mb:.2f} MB ({ceiling_bytes:,} bytes)")
    print("-" * banner_width)
    print(f"{'#':<3} {'Artifact File':<36} {'Size':<16} {'% Total':<8} {'Originating Pipeline':<20}")
    print("-" * banner_width)

    for i, rec in enumerate(file_records, 1):
        size_str = f"{rec['size_mb']:.2f} MB" if rec['size_mb'] >= 0.1 else f"{rec['size_bytes'] / 1024:.1f} KB"
        print(f"{i:<3} {rec['name']:<36} {size_str:<16} {rec['percentage_of_total']:>5.1f}%  {rec['producer']}")

    print("-" * banner_width)
    print(f"TOTAL COMBINED SIZE: {total_mb:.2f} MB ({total_bytes:,} bytes)")
    budget_used_pct = (total_bytes / ceiling_bytes * 100.0) if ceiling_bytes > 0 else 0.0
    print(f"BUDGET UTILIZATION:  {budget_used_pct:.1f}% of {ceiling_mb:.1f}MB ceiling")

    audit_result: Dict[str, Any] = {
        "models_dir": str(target_dir),
        "files": file_records,
        "total_bytes": total_bytes,
        "total_mb": total_mb,
        "ceiling_bytes": ceiling_bytes,
        "ceiling_mb": ceiling_mb,
        "overage_bytes": overage_bytes,
        "overage_mb": overage_mb,
        "budget_used_percent": budget_used_pct,
        "is_within_limit": is_within_limit,
        "largest_contributors": file_records[:3],
    }

    if not is_within_limit:
        overage_pct = (overage_bytes / ceiling_bytes) * 100.0
        print("\n" + "=" * banner_width)
        print(" [CRITICAL FAILURE] ARTIFACT FOOTPRINT CEILING EXCEEDED!")
        print("=" * banner_width)
        print(f"Total Size:     {total_mb:.2f} MB ({total_bytes:,} bytes)")
        print(f"Allowed Limit:  {ceiling_mb:.2f} MB ({ceiling_bytes:,} bytes)")
        print(f"EXACT OVERAGE:  +{overage_mb:.2f} MB (+{overage_bytes:,} bytes, +{overage_pct:.1f}% over limit)")
        print("-" * banner_width)
        print("LARGEST CONTRIBUTORS FLAGGED FOR OPTIMIZATION/PRUNING:")
        for rank, rec in enumerate(file_records[:3], 1):
            print(f"  {rank}. {rec['name']} - {rec['size_mb']:.2f} MB ({rec['percentage_of_total']:.1f}% of total) [{rec['producer']}]")
        print("=" * banner_width)

        if enforce_assertion:
            largest_names = ", ".join(f"{r['name']} ({r['size_mb']:.2f}MB)" for r in file_records[:3])
            error_msg = (
                f"Artifact size ceiling exceeded! Total size {total_mb:.2f} MB exceeds "
                f"{ceiling_mb:.2f} MB ceiling by {overage_mb:.2f} MB ({overage_bytes:,} bytes). "
                f"Largest contributors to optimize first: {largest_names}"
            )
            raise AssertionError(error_msg)
    else:
        headroom_bytes = ceiling_bytes - total_bytes
        headroom_mb = headroom_bytes / BYTES_PER_MB
        print(f"HEADROOM REMAINING:  {headroom_mb:.2f} MB ({headroom_bytes:,} bytes)")
        print("STATUS:              [PASSED] Artifact footprint within architecture spec Section 5.2.")
        print("=" * banner_width)

    return audit_result


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Audit model artifact sizes against Architecture Spec §5.2 (50MB ceiling)."
    )
    parser.add_argument(
        "--models-dir",
        type=str,
        default=None,
        help="Path to models directory (auto-detected if omitted).",
    )
    parser.add_argument(
        "--ceiling-mb",
        type=float,
        default=DEFAULT_CEILING_MB,
        help=f"Maximum allowed total size in MB (default: {DEFAULT_CEILING_MB} MB).",
    )
    parser.add_argument(
        "--no-enforce",
        action="store_true",
        help="Report sizes without raising an assertion error if ceiling is exceeded.",
    )

    args = parser.parse_args()

    try:
        audit_artifact_sizes(
            models_dir=args.models_dir,
            ceiling_mb=args.ceiling_mb,
            enforce_assertion=not args.no_enforce,
        )
    except AssertionError as e:
        print(f"\nAssertionError: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
