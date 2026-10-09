"""Automated Regression Suite for XLSX Expansion and Memory Evidence (WS-C).

Verifies:
1. settings constants for XLSX expansion guard and uncompressed size cap.
2. In-memory generation of realistic XLSX files.
3. Fast pre-parse rejection (HTTP 413 in < 1s) for workbooks exceeding 100 MB uncompressed XML.
4. Acceptance of workbooks within the 100 MB uncompressed ceiling.
"""
from __future__ import annotations

import io
import time
import zipfile
import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient

from config.settings import settings
from main import app
from scripts.measure_xlsx_expansion import build_realistic_xlsx
from src.parsers.sanitization import check_dangerous_and_magic_bytes

client = TestClient(app)


def test_xlsx_settings_expansion_guards_configured():
    """Verify settings defines the XLSX expansion ratio guard and uncompressed cap."""
    assert settings.MAX_XLSX_UNCOMPRESSED_BYTES == 100 * 1024 * 1024
    assert settings.XLSX_EXPANSION_RATIO_GUARD == 100


def test_xlsx_12mb_exceeding_100mb_uncompressed_rejected_413():
    """Verify ~12 MB compressed XLSX (168 MB uncompressed) is rejected pre-parse with HTTP 413 in < 1s."""
    content, comp_mb, uncomp_mb, ratio = build_realistic_xlsx(num_rows=570_000, num_sheets=2)
    assert comp_mb > 10.0
    assert uncomp_mb > 100.0  # Exceeds 100 MB uncompressed cap

    t0 = time.perf_counter()
    with pytest.raises(HTTPException) as exc_info:
        check_dangerous_and_magic_bytes(content, "xlsx")
    elapsed = time.perf_counter() - t0

    assert exc_info.value.status_code == 413
    assert "File uncompressed size exceeds limit" in exc_info.value.detail
    assert "max is 100 MB" in exc_info.value.detail
    assert elapsed < 1.0, f"Gatekeeper rejection took {elapsed:.3f}s (must be < 1.0s)"


def test_xlsx_within_uncompressed_cap_passes_gatekeeper():
    """Verify realistic XLSX under the 100 MB uncompressed cap passes pre-parse gatekeeper."""
    content, comp_mb, uncomp_mb, ratio = build_realistic_xlsx(num_rows=20_000, num_sheets=1)
    assert uncomp_mb < 50.0  # Well within 100 MB uncompressed cap

    t0 = time.perf_counter()
    # Should not raise
    check_dangerous_and_magic_bytes(content, "xlsx")
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.5, f"Gatekeeper check took {elapsed:.3f}s"


def test_xlsx_expansion_ratio_and_compressed_ceiling_relation():
    """Verify relationship between expansion ratio, compressed size, and uncompressed cap."""
    cap_mb = settings.MAX_XLSX_UNCOMPRESSED_BYTES / (1024 * 1024)
    # At typical ~8.5x expansion ratio (Online Retail), ceiling is ~11.8 MB compressed
    implied_ceiling_at_8_5x = cap_mb / 8.5
    assert 11.0 < implied_ceiling_at_8_5x < 13.0

    # At typical ~14x expansion ratio (synthetic tabular), ceiling is ~7.1 MB compressed
    implied_ceiling_at_14x = cap_mb / 14.0
    assert 6.5 < implied_ceiling_at_14x < 7.5
