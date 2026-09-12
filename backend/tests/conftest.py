"""Pytest fixtures and test data generators for Foresight backend tests."""

import io
import pytest
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient
from pypdf import PdfWriter
import docx
import openpyxl

from app.main import app
from app.config import settings


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


@pytest.fixture
def sample_tabular_df():
    """Sample DataFrame matching ingestion, profiling, and modeling tests."""
    return pd.DataFrame({
        "age": [25.0, 30.0, np.nan, 40.0, 50.0],
        "salary": [50000.0, 60000.0, 70000.0, np.nan, 90000.0],
        "department": ["Eng", "Sales", "HR", "Eng", None],
        "is_active": [True, False, True, True, False],
    })


@pytest.fixture
def sample_csv_bytes(sample_tabular_df):
    """CSV bytes generated from sample DataFrame (5 rows, 4 columns)."""
    buf = io.StringIO()
    sample_tabular_df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


@pytest.fixture
def sample_tsv_bytes(sample_tabular_df):
    """TSV bytes generated from sample DataFrame."""
    buf = io.StringIO()
    sample_tabular_df.to_csv(buf, sep="\t", index=False)
    return buf.getvalue().encode("utf-8")


@pytest.fixture
def sample_xlsx_bytes(sample_tabular_df):
    """Valid XLSX bytes generated via openpyxl."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        sample_tabular_df.to_excel(writer, index=False)
    return buf.getvalue()


@pytest.fixture
def sample_parquet_bytes():
    """Valid Parquet bytes with 4 rows and 3 columns."""
    df = pd.DataFrame({
        "col_a": [1.0, 2.0, 3.0, 4.0],
        "col_b": [10, 20, 30, 40],
        "col_c": ["x", "y", "z", "w"],
    })
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    return buf.getvalue()


@pytest.fixture
def sample_pdf_bytes():
    """Valid PDF bytes generated cleanly via pypdf."""
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=144)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture
def sample_docx_bytes():
    """Valid DOCX bytes generated via python-docx."""
    doc = docx.Document()
    doc.add_heading("Foresight Research Dossier", level=1)
    doc.add_paragraph("This is a sample document for testing Engine C ingestion.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def sample_txt_bytes():
    """Valid plain text bytes."""
    return b"Foresight plain text report content.\nLine 2: local intelligence."


@pytest.fixture
def sample_md_bytes():
    """Valid markdown bytes."""
    return b"# Markdown Executive Report\n\n- Point A\n- Point B\n"
