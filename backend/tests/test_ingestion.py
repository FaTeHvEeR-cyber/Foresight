"""Test suite for ingestion across supported tabular and document formats."""

import io
from fastapi import status


def test_upload_csv(client, sample_csv_bytes):
    files = {"file": ("dataset.csv", io.BytesIO(sample_csv_bytes), "text/csv")}
    res = client.post("/api/upload", files=files)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["detectedKind"] == "tabular"
    assert data["detectedFormat"] == "csv"
    assert data["rowCount"] == 5
    assert data["columnCount"] == 4
    assert len(data["columns"]) == 4
    assert data["memoryUsageBytes"] > 0
    assert data["fileId"].startswith("f_")


def test_upload_tsv(client, sample_tsv_bytes):
    files = {"file": ("data.tsv", io.BytesIO(sample_tsv_bytes), "text/tab-separated-values")}
    res = client.post("/api/upload", files=files)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["detectedKind"] == "tabular"
    assert data["detectedFormat"] == "tsv"
    assert data["rowCount"] == 5


def test_upload_xlsx(client, sample_xlsx_bytes):
    files = {"file": ("sheet.xlsx", io.BytesIO(sample_xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    res = client.post("/api/upload", files=files)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["detectedKind"] == "tabular"
    assert data["detectedFormat"] == "xlsx"
    assert data["rowCount"] == 5


def test_upload_parquet(client, sample_parquet_bytes):
    files = {"file": ("records.parquet", io.BytesIO(sample_parquet_bytes), "application/octet-stream")}
    res = client.post("/api/upload", files=files)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["detectedKind"] == "tabular"
    assert data["detectedFormat"] == "parquet"
    assert data["rowCount"] == 4


def test_upload_pdf(client, sample_pdf_bytes):
    files = {"file": ("dossier.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
    res = client.post("/api/upload", files=files)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["detectedKind"] == "document"
    assert data["detectedFormat"] == "pdf"
    assert data["rowCount"] >= 1


def test_upload_docx(client, sample_docx_bytes):
    files = {"file": ("summary.docx", io.BytesIO(sample_docx_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    res = client.post("/api/upload", files=files)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["detectedKind"] == "document"
    assert data["detectedFormat"] == "docx"
    assert data["rowCount"] > 0


def test_upload_txt(client, sample_txt_bytes):
    files = {"file": ("notes.txt", io.BytesIO(sample_txt_bytes), "text/plain")}
    res = client.post("/api/upload", files=files)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["detectedKind"] == "document"
    assert data["detectedFormat"] == "txt"
    assert data["rowCount"] >= 1


def test_upload_md(client, sample_md_bytes):
    files = {"file": ("report.md", io.BytesIO(sample_md_bytes), "text/markdown")}
    res = client.post("/api/upload", files=files)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["detectedKind"] == "document"
    assert data["detectedFormat"] == "md"
    assert data["rowCount"] > 0


def test_health_check(client):
    res = client.get("/api/health")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["status"] == "healthy"
    assert data["maxFileSizeBytes"] == 25 * 1024 * 1024
    assert data["rateLimitingEnabled"] is False
