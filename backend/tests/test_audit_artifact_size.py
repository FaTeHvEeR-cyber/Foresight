"""Tests for Artifact Size Audit Script (backend/scripts/audit_artifact_size.py).

Validates:
1. Scanning models directory identifies all .joblib artifacts.
2. Correctly reports individual and total combined file sizes.
3. Successfully asserts within the 50MB ceiling on existing production models.
4. Fails loudly with exact overage calculation and flags the largest contributors
   when the artifact footprint exceeds the ceiling.
"""

import sys
from pathlib import Path
import pytest

from scripts.audit_artifact_size import (
    DEFAULT_CEILING_MB,
    BYTES_PER_MB,
    audit_artifact_sizes,
    format_bytes,
    resolve_models_directory,
)


def test_format_bytes_utility():
    """Verify human-readable byte formatting helper."""
    assert "500 B" == format_bytes(500)
    assert "1.50 KB" in format_bytes(1536)
    assert "2.00 MB" in format_bytes(2 * 1024 * 1024)
    assert "1.00 GB" in format_bytes(1024 * 1024 * 1024)


def test_audit_production_models_passes():
    """Test that existing serialized models in models/ pass the 50MB ceiling."""
    result = audit_artifact_sizes(enforce_assertion=True)

    assert result["is_within_limit"] is True
    assert result["total_bytes"] > 0
    assert result["total_mb"] < DEFAULT_CEILING_MB
    assert result["overage_bytes"] == 0
    assert result["overage_mb"] == 0.0

    # Verify that expected models from all 3 pipelines are scanned
    filenames = {f["name"] for f in result["files"]}
    # Engine A
    assert "ridge_baseline.joblib" in filenames
    assert "xgboost_primary.joblib" in filenames
    assert "mlp_benchmark.joblib" in filenames
    # Engine B Anomaly
    assert "isolation_forest.joblib" in filenames
    # Engine B Clustering
    assert "kmeans_k4.joblib" in filenames
    assert "pca_2d.joblib" in filenames


def test_audit_fails_loudly_when_ceiling_exceeded(tmp_path):
    """Verify that audit_artifact_sizes raises AssertionError with exact overage when ceiling is exceeded."""
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)

    # Create dummy artifacts that exceed a 5MB ceiling:
    # file 1: 4MB
    # file 2: 3MB
    # Total = 7MB -> overage = 2MB
    file1 = models_dir / "large_model_a.joblib"
    file2 = models_dir / "large_model_b.joblib"
    file3 = models_dir / "small_model.joblib"

    file1.write_bytes(b"0" * (4 * 1024 * 1024))
    file2.write_bytes(b"0" * (3 * 1024 * 1024))
    file3.write_bytes(b"0" * (512 * 1024))

    ceiling_mb = 5.0
    expected_total_bytes = 4 * 1024 * 1024 + 3 * 1024 * 1024 + 512 * 1024
    expected_overage_bytes = expected_total_bytes - int(ceiling_mb * BYTES_PER_MB)

    with pytest.raises(AssertionError) as exc_info:
        audit_artifact_sizes(models_dir=models_dir, ceiling_mb=ceiling_mb, enforce_assertion=True)

    error_msg = str(exc_info.value)
    # Fail loudly with exact overage amount
    assert "Artifact size ceiling exceeded!" in error_msg
    assert f"{expected_overage_bytes:,} bytes" in error_msg
    assert "2.50 MB" in error_msg
    # Flag largest contributors to optimize first
    assert "large_model_a.joblib" in error_msg
    assert "large_model_b.joblib" in error_msg


def test_audit_without_assertion_returns_metrics(tmp_path):
    """Verify that audit_artifact_sizes can return audit metrics without raising when enforce_assertion=False."""
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)

    test_file = models_dir / "test_model.joblib"
    test_file.write_bytes(b"A" * (2 * 1024 * 1024))

    result = audit_artifact_sizes(models_dir=models_dir, ceiling_mb=1.0, enforce_assertion=False)

    assert result["is_within_limit"] is False
    assert result["total_bytes"] == 2 * 1024 * 1024
    assert result["ceiling_bytes"] == 1 * 1024 * 1024
    assert result["overage_bytes"] == 1 * 1024 * 1024
    assert len(result["largest_contributors"]) == 1
    assert result["largest_contributors"][0]["name"] == "test_model.joblib"
