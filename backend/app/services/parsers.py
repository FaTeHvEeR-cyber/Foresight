"""In-memory file parsers for tabular and document formats."""

import io
import pandas as pd
from pypdf import PdfReader
import docx

from app.models.schemas import DetectedFormat


def parse_tabular_file(
    content: bytes,
    detected_format: DetectedFormat,
) -> pd.DataFrame:
    """Parse raw bytes into a pandas DataFrame without writing to disk."""
    bio = io.BytesIO(content)

    if detected_format == "csv":
        # Handle delimiter fallback if needed
        try:
            return pd.read_csv(bio)
        except Exception:
            bio.seek(0)
            return pd.read_csv(bio, sep=None, engine="python")

    elif detected_format == "tsv":
        return pd.read_csv(bio, sep="\t")

    elif detected_format == "parquet":
        return pd.read_parquet(bio)

    elif detected_format in ("xlsx", "xls"):
        return pd.read_excel(bio, engine="openpyxl")

    raise ValueError(f"Unsupported tabular format: {detected_format}")


def parse_document_file(
    content: bytes,
    detected_format: DetectedFormat,
) -> str:
    """Extract clean text content from document files in memory."""
    if detected_format in ("txt", "md"):
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1", errors="replace")

    elif detected_format == "pdf":
        bio = io.BytesIO(content)
        reader = PdfReader(bio)
        pages_text = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pages_text.append(t)
        return "\n\n".join(pages_text)

    elif detected_format == "docx":
        bio = io.BytesIO(content)
        doc = docx.Document(bio)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)

    raise ValueError(f"Unsupported document format: {detected_format}")
