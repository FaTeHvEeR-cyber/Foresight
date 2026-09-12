"""Unit tests for document parser module."""

import io
import pytest
from pypdf import PdfWriter
import docx

from src.parsers.document_parser import (
    DocumentParseError,
    parse_document,
    _detect_text_tables,
)


def _create_pdf_with_text(pages_text: list[str]) -> bytes:
    """Create in-memory PDF with text across pages using pypdf."""
    from pypdf.generic import DictionaryObject, NameObject, TextStringObject
    # Using reportlab or basic pypdf writer
    # pypdf Writer can add blank pages and add annotations, or we can use conftest approach
    writer = PdfWriter()
    for text in pages_text:
        page = writer.add_blank_page(width=300, height=200)
        # Note: PdfWriter add_blank_page creates pages without text streams directly,
        # but pypdf can clone or we can write a basic raw PDF string
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestDocumentParser:
    """Tests for parse_document across supported formats and failure modes."""

    # -------------------------------------------------------------------------
    # PDF Tests
    # -------------------------------------------------------------------------
    def test_parse_pdf_blank_page(self, sample_pdf_bytes):
        """Test parsing valid PDF with a single blank page."""
        result = parse_document(sample_pdf_bytes, "pdf")
        assert isinstance(result, dict)
        assert "raw_text" in result
        assert "page_or_section_count" in result
        assert "has_embedded_tables" in result
        assert result["page_or_section_count"] == 1
        assert result["has_embedded_tables"] is False

    def test_parse_pdf_corrupted_raises_error(self):
        """Corrupted PDF bytes must raise DocumentParseError."""
        corrupted = b"%PDF-1.4\ncorrupted gibberish without xref or trailer"
        with pytest.raises(DocumentParseError, match="Failed to parse PDF document"):
            parse_document(corrupted, "pdf")

    def test_parse_pdf_empty_raises_error(self):
        """Empty PDF bytes must raise DocumentParseError."""
        with pytest.raises(DocumentParseError, match="PDF document is empty"):
            parse_document(b"", "pdf")

    # -------------------------------------------------------------------------
    # DOCX Tests
    # -------------------------------------------------------------------------
    def test_parse_docx_valid(self, sample_docx_bytes):
        """Valid docx with title and paragraph should extract text cleanly."""
        result = parse_document(sample_docx_bytes, "docx")
        assert "Foresight Research Dossier" in result["raw_text"]
        assert "This is a sample document for testing Engine C ingestion." in result["raw_text"]
        assert result["page_or_section_count"] >= 1
        assert result["has_embedded_tables"] is False

    def test_parse_docx_with_table(self):
        """DOCX with embedded table must set has_embedded_tables=True and include cell text."""
        doc = docx.Document()
        doc.add_heading("Financial Summary", level=1)
        doc.add_paragraph("Quarterly metrics:")
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Metric"
        table.cell(0, 1).text = "Value"
        table.cell(1, 0).text = "Revenue"
        table.cell(1, 1).text = "$1.2M"

        buf = io.BytesIO()
        doc.save(buf)
        docx_bytes = buf.getvalue()

        result = parse_document(docx_bytes, ".docx")
        assert result["has_embedded_tables"] is True
        assert "Metric | Value" in result["raw_text"]
        assert "Revenue | $1.2M" in result["raw_text"]
        assert result["page_or_section_count"] >= 1

    def test_parse_docx_corrupted_raises_error(self):
        """Corrupted docx bytes must raise DocumentParseError."""
        corrupted = b"PK\x03\x04corrupted_not_a_valid_docx"
        with pytest.raises(DocumentParseError, match="Failed to parse DOCX document"):
            parse_document(corrupted, "docx")

    def test_parse_docx_empty_raises_error(self):
        """Empty DOCX bytes must raise DocumentParseError."""
        with pytest.raises(DocumentParseError, match="DOCX document is empty"):
            parse_document(b"", "docx")

    # -------------------------------------------------------------------------
    # TXT Tests
    # -------------------------------------------------------------------------
    def test_parse_txt_simple(self, sample_txt_bytes):
        """Valid plain text document."""
        result = parse_document(sample_txt_bytes, "txt")
        assert "Foresight plain text report content." in result["raw_text"]
        assert result["page_or_section_count"] == 1
        assert result["has_embedded_tables"] is False

    def test_parse_txt_with_form_feeds(self):
        """Text with form feeds (\x0c) should count pages accurately."""
        content = "Page 1 intro\x0cPage 2 body\x0cPage 3 conclusion".encode("utf-8")
        result = parse_document(content, "txt")
        assert result["page_or_section_count"] == 3
        assert result["has_embedded_tables"] is False

    def test_parse_txt_with_ascii_table(self):
        """Text containing ASCII table borders should trigger has_embedded_tables."""
        table_text = (
            "Quarterly figures:\n"
            "+---------+---------+\n"
            "| Quarter | Revenue |\n"
            "+---------+---------+\n"
            "| Q1      | 100     |\n"
            "+---------+---------+\n"
        ).encode("utf-8")
        result = parse_document(table_text, "txt")
        assert result["has_embedded_tables"] is True

    def test_parse_txt_with_tsv_table(self):
        """Text containing tab-separated rows should trigger has_embedded_tables."""
        tsv_text = "Name\tAge\tCity\nAlice\t30\tNYC\nBob\t25\tSF\n".encode("utf-8")
        result = parse_document(tsv_text, "txt")
        assert result["has_embedded_tables"] is True

    def test_parse_txt_empty(self):
        """Empty plain text should yield 0 section count and empty string."""
        result = parse_document(b"", "txt")
        assert result["raw_text"] == ""
        assert result["page_or_section_count"] == 0
        assert result["has_embedded_tables"] is False

    # -------------------------------------------------------------------------
    # MD Tests
    # -------------------------------------------------------------------------
    def test_parse_md_sections(self):
        """Markdown with headings should count sections by headers."""
        md_text = (
            "# Main Title\n\nIntroduction.\n\n"
            "## Methodology\n\nDetails.\n\n"
            "### Data Analysis\n\nFindings.\n\n"
            "## Conclusion\n\nSummary."
        ).encode("utf-8")
        result = parse_document(md_text, "md")
        assert result["page_or_section_count"] == 4
        assert "Main Title" in result["raw_text"]
        assert result["has_embedded_tables"] is False

    def test_parse_md_with_table(self):
        """Markdown with markdown table syntax should trigger has_embedded_tables."""
        md_text = (
            "# Summary\n\n"
            "| Header 1 | Header 2 |\n"
            "| -------- | -------- |\n"
            "| Value A  | Value B  |\n"
            "| Value C  | Value D  |\n"
        ).encode("utf-8")
        result = parse_document(md_text, ".md")
        assert result["has_embedded_tables"] is True
        assert result["page_or_section_count"] == 1

    def test_parse_md_empty(self):
        """Empty markdown should return empty text and 0 sections."""
        result = parse_document(b"", "md")
        assert result["raw_text"] == ""
        assert result["page_or_section_count"] == 0
        assert result["has_embedded_tables"] is False

    # -------------------------------------------------------------------------
    # Edge Cases & Validation
    # -------------------------------------------------------------------------
    def test_unsupported_extension_raises_error(self):
        """Unsupported extension must raise DocumentParseError."""
        with pytest.raises(DocumentParseError, match="Unsupported document extension: 'csv'"):
            parse_document(b"col1,col2\n1,2", "csv")

    def test_empty_extension_raises_error(self):
        """Empty extension must raise DocumentParseError."""
        with pytest.raises(DocumentParseError, match="Extension cannot be empty"):
            parse_document(b"hello", "")

    def test_invalid_input_type_raises_error(self):
        """Passing non-bytes must raise DocumentParseError."""
        with pytest.raises(DocumentParseError, match="Expected bytes or bytearray"):
            parse_document("not bytes", "txt")  # type: ignore

    @pytest.mark.parametrize("ext", [".PDF", "pdf", "Docx", ".DOCX", " TXT ", ".md", "Md"])
    def test_extension_normalization(self, ext):
        """Extensions with leading dot, mixed case, or whitespace should normalize."""
        text_bytes = b"# Header\nContent"
        # For pdf and docx, pass appropriate minimal content
        if "pdf" in ext.lower():
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            buf = io.BytesIO()
            writer.write(buf)
            data = buf.getvalue()
        elif "docx" in ext.lower():
            doc = docx.Document()
            doc.add_paragraph("Test")
            buf = io.BytesIO()
            doc.save(buf)
            data = buf.getvalue()
        else:
            data = text_bytes

        result = parse_document(data, ext)
        assert isinstance(result, dict)
        assert "raw_text" in result

    def test_table_detection_heuristics(self):
        """Verify individual heuristics in _detect_text_tables."""
        # Empty / whitespace
        assert _detect_text_tables("") is False
        assert _detect_text_tables("   \n\t\n  ") is False

        # Regular sentences
        assert _detect_text_tables("Hello world.\nThis is a simple paragraph.") is False

        # Markdown table
        assert _detect_text_tables("| A | B |\n|---|---|\n| 1 | 2 |") is True

        # HTML table
        assert _detect_text_tables("<table><tr><td>Cell</td></tr></table>") is True

        # Unicode box
        assert _detect_text_tables("┌───┬───┐\n│ A │ B │\n└───┴───┘") is True

        # Multi-column aligned spaces
        aligned = (
            "ID       Name       Score\n"
            "001      Alpha      98.5\n"
            "002      Beta       89.2\n"
        )
        assert _detect_text_tables(aligned) is True
