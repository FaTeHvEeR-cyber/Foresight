"""Security gatekeeper & file format validation service."""

import io
import zipfile
from typing import Optional, Tuple
from fastapi import HTTPException, status

from app.config import settings
from app.models.schemas import DetectedFileKind, DetectedFormat

PDF_MAGIC = b"%PDF-"
PARQUET_MAGIC = b"PAR1"
XLS_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"\x50\x4b\x03\x04"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class FileValidationError(HTTPException):
    """Specific validation exception for rejected files."""
    def __init__(self, status_code: int = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail: str = ""):
        super().__init__(status_code=status_code, detail=detail)


def validate_file_size(size_bytes: int) -> None:
    """Ensure file size adheres to the 25MB hard guardrail."""
    if size_bytes <= 0:
        raise FileValidationError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded. Foresight requires valid non-empty files."
        )
    if size_bytes > settings.MAX_FILE_SIZE_BYTES:
        max_mb = settings.MAX_FILE_SIZE_BYTES / (1024 * 1024)
        file_mb = size_bytes / (1024 * 1024)
        raise FileValidationError(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the 25MB limit ({file_mb:.2f} MB uploaded, max is {max_mb:.0f} MB)."
        )


def _check_dangerous_signatures(content: bytes) -> None:
    """Detect and reject dangerous executable or disallowed binary headers."""
    if content.startswith(b"MZ"):
        raise FileValidationError(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Disallowed binary signature detected: Windows executable (Executable binaries disallowed)"
        )
    if content.startswith(b"\x7fELF"):
        raise FileValidationError(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Disallowed binary signature detected: Linux ELF (Executable binaries disallowed)"
        )
    if content.startswith(b"#!"):
        raise FileValidationError(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Disallowed binary signature detected: Script / shell executable (Executable binaries disallowed)"
        )
    if content.startswith(PNG_MAGIC):
        raise FileValidationError(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Disallowed binary signature detected: PNG image (disallowed)"
        )


def validate_file_type_and_signatures(
    filename: str,
    content: bytes,
    content_type: Optional[str] = None,
) -> Tuple[DetectedFileKind, DetectedFormat]:
    """
    Validate file extension, MIME types, and magic bytes.
    Raises FileValidationError with HTTP 415 or 400 on failure.
    """
    if len(content) == 0:
        raise FileValidationError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded. Foresight requires valid non-empty files."
        )

    # Check extension first
    parts = filename.rsplit(".", 1)
    if len(parts) < 2 or not parts[1]:
        raise FileValidationError(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File '{filename}' has no extension. Foresight requires a valid extension (disallowed)."
        )

    ext = parts[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise FileValidationError(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file format and Unsupported file extension '.{ext}' (disallowed). "
                f"Accepted formats: {', '.join(sorted(settings.ALLOWED_EXTENSIONS))}."
            )
        )

    # Check dangerous executable signatures
    _check_dangerous_signatures(content)

    # Format-specific signature verification
    if ext == "pdf":
        if not content.startswith(PDF_MAGIC):
            raise FileValidationError(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Missing %PDF- file signature"
            )
        return "document", "pdf"

    elif ext == "parquet":
        if not content.startswith(PARQUET_MAGIC):
            raise FileValidationError(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Missing PAR1 magic byte signature"
            )
        return "tabular", "parquet"

    elif ext in ("xlsx", "docx"):
        if not content.startswith(ZIP_MAGIC):
            raise FileValidationError(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Invalid ZIP archive: missing Office Open XML ZIP header"
            )
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                namelist = zf.namelist()
                if "[Content_Types].xml" not in namelist:
                    raise FileValidationError(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail="Invalid ZIP archive: missing Office Open XML [Content_Types].xml"
                    )
        except zipfile.BadZipFile:
            raise FileValidationError(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Invalid ZIP archive: corrupted Office Open XML container"
            )

        if ext == "xlsx":
            return "tabular", "xlsx"
        else:
            return "document", "docx"

    elif ext == "xls":
        if not content.startswith(XLS_OLE_MAGIC):
            raise FileValidationError(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Corrupted or invalid XLS file (missing OLE header)"
            )
        return "tabular", "xls"

    elif ext in ("csv", "tsv"):
        if b"\x00" in content:
            raise FileValidationError(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Contains null byte binary data: Binary or malformed content detected (disallowed)."
            )
        return "tabular", ext  # type: ignore

    elif ext in ("txt", "md"):
        if b"\x00" in content:
            raise FileValidationError(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Contains null byte binary data: Binary or malformed content detected (disallowed)."
            )
        return "document", ext  # type: ignore

    raise FileValidationError(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=f"Unsupported file format: {ext}"
    )


# Alias for backward compatibility
validate_and_classify_file = validate_file_type_and_signatures
