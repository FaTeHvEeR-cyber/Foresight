"""Sanitization and security validation service for incoming files.

Provides:
- validate_mime_and_extension: MIME type and extension validation against settings,
  rejecting files if the declared MIME type and extension disagree (defense against
  renamed files).
- validate_file_size: Enforces MAX_FILE_SIZE_MB guardrail on file bytes.
- sanitize_tabular_cells: Neutralizes formula-injection prefixes (=, @, +, -) from
  tabular string cells per spec §4.2 by prepending a single quote or stripping
  the prefix character.
- MimeTypeError & FileSizeError: Specific, clear exceptions for error handling in main.py.
"""

from typing import Any, Dict, Optional, Set, Union
from fastapi import HTTPException
import pandas as pd

try:
    from config.settings import settings
except ImportError:
    from app.config import settings


class SanitizationError(Exception):
    """Base exception for sanitization and file validation errors."""

    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class MimeTypeError(SanitizationError):
    """Raised when file extension or MIME type is disallowed or they disagree.

    Attributes:
        detail: Human-readable error explanation.
        filename: Name of the rejected file (if provided).
        content_type: Declared MIME type (if provided).
        extension: Parsed file extension (if detected).
        status_code: HTTP status code recommendation (defaults to 415).
    """

    def __init__(
        self,
        detail: str,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        extension: Optional[str] = None,
        status_code: int = 415,
    ):
        super().__init__(detail, status_code=status_code)
        self.filename = filename
        self.content_type = content_type
        self.extension = extension


class FileSizeError(SanitizationError):
    """Raised when file size exceeds configured limits or is invalid/empty.

    Attributes:
        detail: Human-readable error explanation.
        file_size_bytes: Actual file size in bytes (if known).
        max_file_size_mb: Maximum permitted size in megabytes.
        status_code: HTTP status code recommendation (413 for oversized, 400 for empty).
    """

    def __init__(
        self,
        detail: str,
        file_size_bytes: Optional[int] = None,
        max_file_size_mb: Optional[int] = None,
        status_code: int = 413,
    ):
        super().__init__(detail, status_code=status_code)
        self.file_size_bytes = file_size_bytes
        self.max_file_size_mb = max_file_size_mb


# Mapping of supported file extensions to compatible declared MIME types.
# Enforces defense against renamed files (e.g. executable/PDF renamed to .csv).
EXTENSION_TO_ALLOWED_MIMES: Dict[str, Set[str]] = {
    "csv": {
        "text/csv",
        "text/plain",
        "application/vnd.ms-excel",
    },
    "tsv": {
        "text/tab-separated-values",
        "text/plain",
        "text/csv",
    },
    "xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },
    "xls": {
        "application/vnd.ms-excel",
    },
    "parquet": {
        "application/vnd.apache.parquet",
        "application/x-parquet",
        "application/octet-stream",
    },
    "pdf": {
        "application/pdf",
    },
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
    "txt": {
        "text/plain",
    },
    "md": {
        "text/markdown",
        "text/plain",
    },
}

# Formula injection prefixes per spec §4.2 and OWASP CSV Injection guidelines
FORMULA_PREFIXES = ("=", "@", "+", "-")


def validate_mime_and_extension(filename: str, content_type: str) -> bool:
    """Validate file extension and declared MIME type against configured allowlists.

    Defends against renamed files by rejecting uploads where the declared MIME
    type and the file extension disagree, not just if either alone is disallowed.

    Args:
        filename: Declared file name with extension.
        content_type: Declared Content-Type / MIME header from the client.

    Returns:
        bool: True if validation passes.

    Raises:
        MimeTypeError: If filename or MIME type is missing, disallowed, or if
            the extension and declared MIME type disagree.
    """
    if not filename or not isinstance(filename, str) or not filename.strip():
        raise MimeTypeError(
            "Filename is missing or empty.",
            filename=filename,
            content_type=content_type,
            status_code=400,
        )

    if not content_type or not isinstance(content_type, str) or not content_type.strip():
        raise MimeTypeError(
            "Content-Type header is missing or empty.",
            filename=filename,
            content_type=content_type,
            status_code=400,
        )

    clean_filename = filename.strip()
    clean_mime = content_type.split(";")[0].strip().lower()

    # Extract extension
    parts = clean_filename.rsplit(".", 1)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise MimeTypeError(
            f"File '{clean_filename}' has no valid extension. Foresight requires an extension.",
            filename=clean_filename,
            content_type=clean_mime,
            status_code=415,
        )

    ext = parts[1].strip().lower()

    # 1. Check extension against settings.ALLOWED_EXTENSIONS
    allowed_extensions = {e.lower().lstrip(".") for e in settings.ALLOWED_EXTENSIONS}
    if ext not in allowed_extensions:
        raise MimeTypeError(
            f"Unsupported file extension '.{ext}'. Allowed extensions: {', '.join(sorted(allowed_extensions))}.",
            filename=clean_filename,
            content_type=clean_mime,
            extension=ext,
            status_code=415,
        )

    # 2. Check MIME type against settings.ALLOWED_MIME_TYPES
    allowed_mime_types = {m.lower().strip() for m in settings.ALLOWED_MIME_TYPES}
    if clean_mime not in allowed_mime_types:
        raise MimeTypeError(
            f"Unsupported MIME type '{clean_mime}'. Allowed MIME types: {', '.join(sorted(allowed_mime_types))}.",
            filename=clean_filename,
            content_type=clean_mime,
            extension=ext,
            status_code=415,
        )

    # 3. Check agreement between declared MIME type and extension (defense against renamed files)
    compatible_mimes = EXTENSION_TO_ALLOWED_MIMES.get(ext, set())
    if clean_mime not in compatible_mimes:
        raise MimeTypeError(
            f"Declared MIME type '{clean_mime}' disagrees with file extension '.{ext}'. "
            f"Expected one of: {', '.join(sorted(compatible_mimes))}.",
            filename=clean_filename,
            content_type=clean_mime,
            extension=ext,
            status_code=415,
        )

    return True


def validate_file_size(file_bytes: Union[bytes, bytearray, memoryview, int]) -> bool:
    """Validate file size against settings.MAX_FILE_SIZE_MB guardrail.

    Args:
        file_bytes: Raw bytes of the uploaded file or total size in bytes.

    Returns:
        bool: True if file size is within limits.

    Raises:
        FileSizeError: If file is empty (0 bytes) or exceeds MAX_FILE_SIZE_MB.
        TypeError: If input is neither bytes nor integer size.
    """
    if file_bytes is None:
        raise FileSizeError(
            "File payload is missing (None).",
            file_size_bytes=0,
            status_code=400,
        )

    if isinstance(file_bytes, (int, float)):
        size_bytes = int(file_bytes)
    elif isinstance(file_bytes, (bytes, bytearray, memoryview)):
        size_bytes = len(file_bytes)
    else:
        raise TypeError(f"Expected bytes or int, got {type(file_bytes).__name__}")

    max_mb = getattr(settings, "MAX_FILE_SIZE_MB", 25)
    max_bytes = getattr(settings, "max_file_size_bytes", max_mb * 1024 * 1024)

    if size_bytes <= 0:
        raise FileSizeError(
            "Empty file uploaded (0 bytes). Foresight requires valid non-empty files.",
            file_size_bytes=size_bytes,
            max_file_size_mb=max_mb,
            status_code=400,
        )

    if size_bytes > max_bytes:
        file_mb = size_bytes / (1024 * 1024)
        raise FileSizeError(
            f"File exceeds the {max_mb}MB limit ({file_mb:.2f} MB uploaded, max is {max_mb} MB).",
            file_size_bytes=size_bytes,
            max_file_size_mb=max_mb,
            status_code=413,
        )

    return True


def sanitize_tabular_cells(
    df: pd.DataFrame,
    method: str = "quote",
    strip_prefix: Optional[bool] = None,
) -> pd.DataFrame:
    """Sanitize tabular DataFrame cells and headers against formula injection attacks (CWE-1236).

    Inspects string cell values and column headers, neutralizing dangerous formula-injection prefixes
    (=, @, +, -) per spec §4.2 by either prepending a single quote (') or stripping
    the leading character.

    Only applies to tabular data string cells and string column headers. Numeric, boolean, datetime,
    and null values are preserved without alteration. The original DataFrame is not mutated.

    Args:
        df: Input pandas DataFrame.
        method: Sanitization method: 'quote' (default, prepends single quote) or
            'strip' (strips leading formula prefix character).
        strip_prefix: Optional boolean convenience flag. If True, forces method='strip'.
            If False, forces method='quote'. If None, defaults to method.

    Returns:
        pd.DataFrame: A new sanitized DataFrame copy.
    """
    if df.empty:
        return df.copy()

    if strip_prefix is not None:
        selected_method = "strip" if strip_prefix else "quote"
    else:
        selected_method = method.lower().strip()

    def _sanitize_val(val: Any) -> Any:
        if not isinstance(val, str) or not val:
            return val
        if val[0] in FORMULA_PREFIXES:
            if selected_method == "strip":
                return val.lstrip("=@+-")
            else:
                return f"'{val}"
        return val

    sanitized_df = df.copy()

    # Neutralize dangerous formula prefixes in column headers
    sanitized_df.columns = [
        _sanitize_val(col) if isinstance(col, str) else col
        for col in sanitized_df.columns
    ]

    for col in sanitized_df.columns:
        series = sanitized_df[col]

        # Skip purely numeric or boolean series
        if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_object_dtype(series):
            continue
        if pd.api.types.is_bool_dtype(series):
            continue

        if isinstance(series.dtype, pd.CategoricalDtype):
            new_categories = [
                _sanitize_val(cat) if isinstance(cat, str) else cat
                for cat in series.cat.categories
            ]
            if len(new_categories) == len(set(new_categories)):
                sanitized_df[col] = series.cat.rename_categories(new_categories)
            else:
                sanitized_df[col] = pd.Categorical(series.astype(object).map(_sanitize_val))
        else:
            sanitized_df[col] = series.map(_sanitize_val)

    return sanitized_df


# Magic byte constants for Phase 2 security gatekeeper
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PARQUET_MAGIC = b"PAR1"
ZIP_MAGIC = b"\x50\x4b\x03\x04"
XLS_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
TABULAR_ALLOWED_EXTENSIONS: Set[str] = {"csv", "tsv", "xlsx", "xls", "parquet", "txt"}


def check_dangerous_and_magic_bytes(content: bytes, ext: str) -> None:
    """Detect and reject dangerous executable headers or corrupted format magic bytes."""
    if content.startswith(b"MZ"):
        raise HTTPException(
            status_code=415,
            detail="Disallowed binary signature detected: Windows executable (Executable binaries disallowed)",
        )
    if content.startswith(b"\x7fELF"):
        raise HTTPException(
            status_code=415,
            detail="Disallowed binary signature detected: Linux ELF (Executable binaries disallowed)",
        )
    if content.startswith(b"#!"):
        raise HTTPException(
            status_code=415,
            detail="Disallowed binary signature detected: Script / shell executable (Executable binaries disallowed)",
        )
    if content.startswith(PNG_MAGIC):
        raise HTTPException(
            status_code=415,
            detail="Disallowed binary signature detected: PNG image (disallowed)",
        )

    # Format-specific magic checks
    if ext == "parquet":
        if not content.startswith(PARQUET_MAGIC):
            raise HTTPException(
                status_code=415,
                detail="Missing PAR1 magic byte signature",
            )
    elif ext == "xlsx":
        if not content.startswith(ZIP_MAGIC):
            raise HTTPException(
                status_code=415,
                detail="Invalid ZIP archive: missing Office Open XML ZIP header",
            )
    elif ext == "xls":
        if not content.startswith(XLS_OLE_MAGIC):
            raise HTTPException(
                status_code=415,
                detail="Corrupted or invalid XLS file (missing OLE header)",
            )
    elif ext in ("csv", "tsv", "txt"):
        if b"\x00" in content:
            raise HTTPException(
                status_code=415,
                detail="Contains null byte binary data: Binary or malformed content detected (disallowed).",
            )


def gatekeep_tabular_upload(
    filename: str,
    content: bytes,
    content_type: Optional[str] = None,
    max_bytes: Optional[int] = None,
) -> str:
    """Phase 2 Security Gatekeeper for tabular file uploads.

    Enforces:
    - 50 MB HTTP 413 guardrail (and 0-byte HTTP 422 rejection)
    - Tabular extension whitelist & MIME consistency (HTTP 415)
    - Magic byte inspection and dangerous binary rejection (HTTP 415)

    Returns:
        str: Normalized lowercase file extension.
    """
    if max_bytes is None:
        max_bytes = getattr(settings, "max_upload_bytes", 50 * 1024 * 1024)

    # 1. Size guardrail: 50MB HTTP 413 (and 0-byte HTTP 422)
    if len(content) > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        file_mb = len(content) / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {max_mb}MB limit ({file_mb:.2f} MB uploaded, max is {max_mb} MB).",
        )
    if len(content) == 0:
        raise HTTPException(
            status_code=422,
            detail="Empty file uploaded (0 bytes). Foresight requires valid non-empty files.",
        )

    # 2. Extension validation
    clean_filename = (filename or "").strip()
    if not clean_filename or "." not in clean_filename:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file format: File '{clean_filename}' has no valid extension. Foresight requires a valid extension (disallowed).",
        )

    ext = clean_filename.rsplit(".", 1)[-1].strip().lower()
    if ext not in TABULAR_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file extension or non-tabular format '.{ext}' (disallowed). "
            f"Accepted tabular formats: {', '.join(sorted(TABULAR_ALLOWED_EXTENSIONS))}.",
        )

    # 3. Declared MIME consistency (defense against renamed files)
    if content_type:
        clean_mime = content_type.split(";")[0].strip().lower()
        if clean_mime and clean_mime not in ("application/octet-stream", "multipart/form-data"):
            compatible_mimes = EXTENSION_TO_ALLOWED_MIMES.get(ext, set())
            if compatible_mimes and clean_mime not in compatible_mimes:
                raise HTTPException(
                    status_code=415,
                    detail=f"Declared MIME type '{clean_mime}' disagrees with file extension '.{ext}'. "
                    f"Expected one of: {', '.join(sorted(compatible_mimes))}.",
                )

    # 4. Magic bytes & dangerous binary headers
    check_dangerous_and_magic_bytes(content, ext)

    return ext

