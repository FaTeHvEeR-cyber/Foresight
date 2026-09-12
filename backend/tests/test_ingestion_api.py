"""End-to-end integration tests for POST /api/upload endpoint."""

from app.services.session_store import session_store


def test_upload_valid_csv(client, sample_csv_bytes):
    """Test successful CSV ingestion, profiling, and modeling data generation."""
    response = client.post(
        "/api/upload",
        files={"file": ("staff.csv", sample_csv_bytes, "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()

    # Verify UploadResponse structure
    assert data["fileName"] == "staff.csv"
    assert data["detectedKind"] == "tabular"
    assert data["detectedFormat"] == "csv"
    assert data["rowCount"] == 5
    assert data["columnCount"] == 4
    assert len(data["columns"]) == 4

    # Verify raw null profile in API response
    raw_profile = data["rawNullProfile"]
    assert raw_profile is not None
    assert raw_profile["age"]["nullCount"] == 1
    assert raw_profile["salary"]["nullCount"] == 1
    assert raw_profile["department"]["nullCount"] == 1
    assert raw_profile["is_active"]["nullCount"] == 0

    # Verify session store contains separate raw and imputed data
    file_id = data["fileId"]
    session = session_store.get_session(file_id)
    assert session is not None
    assert session.raw_dataframe is not None
    assert session.imputed_modeling_data is not None

    # Raw dataframe still has nulls
    assert session.raw_dataframe["age"].isna().sum() == 1
    # Imputed modeling data has 0 nulls in numeric features
    assert session.imputed_modeling_data["age"].isna().sum() == 0
    assert "age_isna" in session.imputed_modeling_data.columns


def test_upload_valid_parquet(client, sample_parquet_bytes):
    """Test successful Parquet ingestion."""
    response = client.post(
        "/api/upload",
        files={"file": ("dataset.parquet", sample_parquet_bytes, "application/octet-stream")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["detectedKind"] == "tabular"
    assert data["detectedFormat"] == "parquet"
    assert data["rowCount"] == 4
    assert data["columnCount"] == 3


def test_upload_valid_pdf(client, sample_pdf_bytes):
    """Test successful PDF document ingestion."""
    response = client.post(
        "/api/upload",
        files={"file": ("whitepaper.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["detectedKind"] == "document"
    assert data["detectedFormat"] == "pdf"
    assert "memoryUsageBytes" in data


def test_upload_empty_file_rejected(client):
    """Test empty file rejection."""
    response = client.post(
        "/api/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert response.status_code == 400
    assert "Empty file uploaded" in response.json()["detail"]


def test_upload_disallowed_mime_rejected(client):
    """Test upload with executable signature rejected with 415."""
    fake_csv = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00data"
    response = client.post(
        "/api/upload",
        files={"file": ("data.csv", fake_csv, "text/csv")},
    )
    assert response.status_code == 415
    assert "Disallowed binary signature" in response.json()["detail"]
