"""In-memory document parser for PDF, DOCX, TXT, and MD formats."""

from __future__ import annotations

import io
import re
from typing import Any, Dict

# Prefer pypdf, with optional pdfplumber fallback/enhancement if installed
try:
    import pdfplumber  # type: ignore[import-untyped,import-not-found]
except ImportError:
    pdfplumber = None

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph
import pypdf


class DocumentParseError(Exception):
    """Exception raised when a document cannot be parsed or is corrupted."""
    pass


_SUPPORTED_EXTENSIONS = {"pdf", "docx", "txt", "md"}


def _detect_text_tables(text: str) -> bool:
    """Best-effort heuristic detection of tabular structures in plain text / markdown.

    Detects:
    - Markdown pipe tables (| header | header | followed by |---|---|)
    - Consecutive pipe-delimited lines (| a | b |)
    - HTML table tags (<table>, <tr>, <td>)
    - ASCII grid tables (+---+---+)
    - Unicode box-drawing tables (e.g., ┌─┬─┐, │, ─)
    - Consecutive tab-delimited rows with 2+ columns
    - Consecutive multi-column rows separated by 2+ whitespace spaces
    """
    if not text or not text.strip():
        return False

    # 1. HTML table markup
    if re.search(r"<table[\s>]", text, re.IGNORECASE):
        return True

    # 2. Markdown table syntax with delimiter row (e.g., |---|---| or |:---:|)
    if re.search(r"\|[^\n\r]+\|\r?\n\s*\|[\s:\-|=]+\|", text):
        return True

    # 3. Consecutive pipe-separated lines
    lines = text.splitlines()
    pipe_rows = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
            pipe_rows += 1
            if pipe_rows >= 2:
                return True
        else:
            pipe_rows = 0

    # 4. ASCII grid borders (e.g., +----+----+)
    if re.search(r"^\s*\+[-+=]+\+[-+=+]+\s*$", text, re.MULTILINE):
        return True

    # 5. Unicode box-drawing characters
    if re.search(r"[┌┬┐├┼┤└┴┘│║═]", text):
        return True

    # 6. Consecutive tab-delimited lines (2+ columns)
    tab_rows = 0
    for line in lines:
        stripped = line.strip()
        if stripped and stripped.count("\t") >= 1 and len(stripped.split("\t")) >= 2:
            tab_rows += 1
            if tab_rows >= 2:
                return True
        else:
            tab_rows = 0

    # 7. Consecutive lines with multiple aligned columns (3+ columns separated by 2+ spaces)
    col_rows = 0
    for line in lines:
        stripped = line.strip()
        if stripped:
            parts = [p for p in re.split(r"\s{2,}", stripped) if p]
            if len(parts) >= 3:
                col_rows += 1
                if col_rows >= 2:
                    return True
            else:
                col_rows = 0
        else:
            col_rows = 0

    return False


def _parse_pdf(file_bytes: bytes) -> Dict[str, Any]:
    """Parse PDF document from in-memory bytes."""
    if not file_bytes:
        raise DocumentParseError("PDF document is empty (0 bytes).")

    bio = io.BytesIO(file_bytes)
    has_tables = False

    # Optional pdfplumber check if installed
    if pdfplumber is not None:
        try:
            with pdfplumber.open(bio) as pdf:
                page_count = len(pdf.pages)
                pages_text = []
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        pages_text.append(extracted)
                    if not has_tables and page.extract_tables():
                        has_tables = True
                raw_text = "\n\n".join(pages_text)
                if not has_tables:
                    has_tables = _detect_text_tables(raw_text)
                return {
                    "raw_text": raw_text,
                    "page_or_section_count": page_count,
                    "has_embedded_tables": has_tables,
                }
        except Exception:
            # Fall back to pypdf if pdfplumber fails
            bio.seek(0)

    try:
        reader = pypdf.PdfReader(bio)
        page_count = len(reader.pages)
        pages_text = []

        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                pages_text.append(extracted)

        raw_text = "\n\n".join(pages_text)

        # Best-effort table detection
        if not has_tables:
            has_tables = _detect_text_tables(raw_text)

        # Also inspect PDF structure tree tags if available
        if not has_tables:
            try:
                root = reader.root_object
                if "/StructTreeRoot" in root:
                    struct_tree = str(root["/StructTreeRoot"])
                    if "/Table" in struct_tree or "/TR" in struct_tree:
                        has_tables = True
            except Exception:
                pass

        return {
            "raw_text": raw_text,
            "page_or_section_count": page_count,
            "has_embedded_tables": has_tables,
        }
    except DocumentParseError:
        raise
    except Exception as e:
        raise DocumentParseError(f"Failed to parse PDF document: {e}") from e


def _parse_docx(file_bytes: bytes) -> Dict[str, Any]:
    """Parse DOCX document from in-memory bytes."""
    if not file_bytes:
        raise DocumentParseError("DOCX document is empty (0 bytes).")

    bio = io.BytesIO(file_bytes)
    try:
        doc = docx.Document(bio)
    except Exception as e:
        raise DocumentParseError(f"Failed to parse DOCX document: {e}") from e

    has_tables = len(doc.tables) > 0
    section_count = len(doc.sections)

    # Extract text from paragraphs and tables in natural document flow
    text_blocks = []
    try:
        for child in doc.element.body:
            if child.tag.endswith("p"):
                p = Paragraph(child, doc)
                if p.text.strip():
                    text_blocks.append(p.text)
            elif child.tag.endswith("tbl"):
                t = Table(child, doc)
                for row in t.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_text:
                        text_blocks.append(row_text)
    except Exception:
        # Fallback to standard paragraphs and tables iteration
        text_blocks = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    text_blocks.append(row_text)

    raw_text = "\n\n".join(text_blocks)
    if not has_tables:
        has_tables = _detect_text_tables(raw_text)

    if not raw_text.strip() and section_count == 0:
        page_or_section_count = 0
    else:
        page_or_section_count = max(1, section_count)

    return {
        "raw_text": raw_text,
        "page_or_section_count": page_or_section_count,
        "has_embedded_tables": has_tables,
    }


def _parse_txt(file_bytes: bytes) -> Dict[str, Any]:
    """Parse plain text document from in-memory bytes."""
    try:
        raw_text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            raw_text = file_bytes.decode("latin-1")
        except Exception as e:
            raise DocumentParseError(f"Failed to decode text document: {e}") from e

    # Page or section count: split on form feed characters (\x0c) if present
    if "\x0c" in raw_text:
        pages = [p for p in raw_text.split("\x0c") if p.strip()]
        page_or_section_count = max(1, len(pages))
    else:
        page_or_section_count = 0 if not raw_text.strip() else 1

    has_tables = _detect_text_tables(raw_text)

    return {
        "raw_text": raw_text,
        "page_or_section_count": page_or_section_count,
        "has_embedded_tables": has_tables,
    }


def _parse_md(file_bytes: bytes) -> Dict[str, Any]:
    """Parse markdown document from in-memory bytes."""
    try:
        raw_text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            raw_text = file_bytes.decode("latin-1")
        except Exception as e:
            raise DocumentParseError(f"Failed to decode markdown document: {e}") from e

    # Count sections demarcated by markdown headings (#, ##, ###, etc.)
    headings = re.findall(r"(?m)^#{1,6}\s+\S", raw_text)
    if headings:
        page_or_section_count = len(headings)
    else:
        page_or_section_count = 0 if not raw_text.strip() else 1

    has_tables = _detect_text_tables(raw_text)

    return {
        "raw_text": raw_text,
        "page_or_section_count": page_or_section_count,
        "has_embedded_tables": has_tables,
    }


def parse_document(file_bytes: bytes, extension: str) -> Dict[str, Any]:
    """Parse document file bytes into extracted text, section count, and table flag.

    Parameters:
        file_bytes: Raw in-memory document bytes.
        extension: File extension string (e.g., 'pdf', '.docx', 'txt', 'md').

    Returns:
        Dict with keys:
            - 'raw_text': str
            - 'page_or_section_count': int
            - 'has_embedded_tables': bool

    Raises:
        DocumentParseError: If file is corrupted, unparseable, or format unsupported.
    """
    if not isinstance(file_bytes, (bytes, bytearray)):
        raise DocumentParseError(f"Expected bytes or bytearray, got {type(file_bytes).__name__}")

    norm_ext = extension.lower().strip().lstrip(".")
    if not norm_ext:
        raise DocumentParseError("Extension cannot be empty.")

    if norm_ext == "pdf":
        return _parse_pdf(bytes(file_bytes))
    elif norm_ext == "docx":
        return _parse_docx(bytes(file_bytes))
    elif norm_ext == "txt":
        return _parse_txt(bytes(file_bytes))
    elif norm_ext == "md":
        return _parse_md(bytes(file_bytes))
    else:
        raise DocumentParseError(
            f"Unsupported document extension: '{extension}'. "
            f"Supported extensions: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
        )
