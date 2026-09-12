"""Test foundational setup for Phase 2: settings, models, and main app."""

from starlette.testclient import TestClient
# pyrefly: ignore [missing-import]
from config.settings import settings
# pyrefly: ignore [missing-import]
from src.models import (
    ColumnDescriptor,
    ColumnNullMetric,
    RawNullProfile,
    UploadResponse,
)
from main import app


def test_settings_configuration():
    """Verify settings defaults and required properties."""
    assert settings.MAX_FILE_SIZE_MB == 25
    assert settings.ENABLE_RATE_LIMITING is False
    assert settings.RATE_LIMIT_REQUESTS_PER_MINUTE == 30
    assert "csv" in settings.ALLOWED_EXTENSIONS
    assert "tsv" in settings.ALLOWED_EXTENSIONS
    assert "xlsx" in settings.ALLOWED_EXTENSIONS
    assert "xls" in settings.ALLOWED_EXTENSIONS
    assert "parquet" in settings.ALLOWED_EXTENSIONS
    assert "pdf" in settings.ALLOWED_EXTENSIONS
    assert "docx" in settings.ALLOWED_EXTENSIONS
    assert "txt" in settings.ALLOWED_EXTENSIONS
    assert "md" in settings.ALLOWED_EXTENSIONS


def test_models_contracts():
    """Verify models mirror frontend contracts and RawNullProfile is separate."""
    col = ColumnDescriptor(
        name="feature_1",
        inferredType="numeric",
        nullCount=5,
        nullPercentage=25.0,
    )
    metric = ColumnNullMetric(
        columnName="feature_1",
        nullCount=5,
        nullPercentage=25.0,
    )
    raw_profile = RawNullProfile(columns=[metric], totalRows=20)

    res = UploadResponse(
        fileId="f-001",
        fileName="dataset.csv",
        fileSizeBytes=4096,
        detectedKind="tabular",
        detectedFormat="csv",
        rowCount=20,
        columnCount=1,
        columns=[col],
        rawNullProfile=raw_profile,
        memoryUsageBytes=8192,
    )

    data = res.model_dump()
    assert data["fileId"] == "f-001"
    assert data["fileName"] == "dataset.csv"
    assert data["detectedKind"] == "tabular"
    assert data["detectedFormat"] == "csv"
    assert data["rowCount"] == 20
    assert data["columnCount"] == 1
    assert data["columns"][0]["name"] == "feature_1"
    assert data["rawNullProfile"]["columns"][0]["columnName"] == "feature_1"
    assert data["memoryUsageBytes"] == 8192


def test_main_app_routes():
    """Verify main app starts with CORS, inert rate limiting, and POST /upload stub."""
    client = TestClient(app)

    # Health check
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"
    assert res_health.json()["rate_limiting_enabled"] is False

    # POST /upload stub
    res_upload = client.post("/upload")
    assert res_upload.status_code == 200
