"""FastAPI Main Application for Foresight backend.

Implements the POST /upload endpoint with:
- In-memory processing via io.BytesIO (no disk writes)
- Validation via sanitization.py (MIME, extension, and file size guardrail)
- Classification of detectedKind based on extension
- Tabular pipeline: parse_tabular → sanitize_tabular_cells → compute_raw_null_profile → impute_for_modeling
- Document pipeline: parse_document
- Wrapped in ephemeral_processing() lifecycle management
- Returns UploadResponse with raw null profile (not imputed data)
"""

import io
from typing import Any, Dict, Optional
import uuid

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from config.settings import settings
from src.memory.lifecycle import ephemeral_processing
from src.models import (
    ColumnDescriptor,
    ColumnNullMetric,
    RawNullProfile,
    UploadResponse,
)
from src.parsers.document_parser import parse_document
from src.parsers.imputation import impute_for_modeling
from src.parsers.sanitization import (
    FileSizeError,
    MimeTypeError,
    SanitizationError,
    sanitize_tabular_cells,
    validate_file_size,
    validate_mime_and_extension,
)
from src.parsers.tabular_parser import (
    compute_raw_null_profile,
    infer_column_types,
    parse_tabular,
)

# In-memory session store mapping file_id to processed dataset parts.
# Keeps raw null profile and imputed modeling data strictly separate.
DATA_STORE: Dict[str, Dict[str, Any]] = {}

TABULAR_EXTENSIONS = {"csv", "tsv", "xlsx", "xls", "parquet"}
DOCUMENT_EXTENSIONS = {"pdf", "docx", "txt", "md"}


class RateLimiterPlaceholderMiddleware(BaseHTTPMiddleware):
    """Placeholder rate-limiting middleware.

    Checks `settings.ENABLE_RATE_LIMITING` and no-ops if False,
    ensuring it is inert during Phases 2-4 and will not throttle local dev/testing.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.ENABLE_RATE_LIMITING:
            # Inert placeholder — no-op
            return await call_next(request)

        # Rate limiting logic scaffold (deferred to Phase 5)
        return await call_next(request)


app = FastAPI(
    title="Foresight Engine API",
    description="Backend API for Foresight data ingestion, statistical modeling, and document intelligence.",
    version="0.2.0",
)

# 1. Rate Limiting Middleware (inert placeholder)
app.add_middleware(RateLimiterPlaceholderMiddleware)

# 2. CORS Middleware allowing Next.js frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "phase": 2,
        "rate_limiting_enabled": settings.ENABLE_RATE_LIMITING,
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
    }


@app.get("/api/health")
async def api_health():
    return {
        "status": "healthy",
        "phase": 2,
        "rate_limiting_enabled": settings.ENABLE_RATE_LIMITING,
        "rateLimitingEnabled": settings.ENABLE_RATE_LIMITING,
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
        "maxFileSizeBytes": settings.MAX_FILE_SIZE_MB * 1024 * 1024,
    }


from fastapi.responses import JSONResponse


@app.post("/upload", response_model=UploadResponse)
@app.post("/api/upload", response_model=UploadResponse)
async def upload(file: Optional[UploadFile] = File(None)):
    """Ingest, validate, profile, and preprocess uploaded dataset or document."""
    # 6. Wrap the whole handler body in the ephemeral_processing() context manager
    with ephemeral_processing():
        if file is None:
            return JSONResponse(status_code=200, content={"message": "Upload stub"})

        filename = file.filename or ""

        # 1. Read the uploaded file into bytes via io.BytesIO (no disk writes)
        raw_contents = await file.read()
        file_io = io.BytesIO(raw_contents)
        file_bytes = file_io.getvalue()

        # 2. Run validate_mime_and_extension and validate_file_size from sanitization.py
        # Return 400 with a clear error if either fails
        try:
            validate_mime_and_extension(filename, file.content_type or "")
            validate_file_size(file_bytes)
        except (SanitizationError, MimeTypeError, FileSizeError) as exc:
            error_msg = getattr(exc, "detail", str(exc))
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Validation failed: {str(exc)}")

        # 3. Classify detectedKind ("tabular" | "document" | "mixed") based on extension
        ext = filename.rsplit(".", 1)[-1].lower().strip() if "." in filename else ""
        if ext in TABULAR_EXTENSIONS:
            detected_kind = "tabular"
        elif ext in DOCUMENT_EXTENSIONS:
            detected_kind = "document"
        else:
            detected_kind = "mixed"

        detected_format = ext
        file_id = f"f_{uuid.uuid4().hex[:12]}"

        # 4. For tabular: parse_tabular → sanitize_tabular_cells → compute_raw_null_profile → impute_for_modeling
        if detected_kind == "tabular":
            try:
                raw_df = parse_tabular(file_bytes, ext)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to parse tabular file '{filename}': {str(exc)}",
                )

            sanitized_df = sanitize_tabular_cells(raw_df)
            raw_null_profile_list = compute_raw_null_profile(sanitized_df)
            imputed_modeling_data = impute_for_modeling(sanitized_df)

            # Store raw profile and imputed data separately
            DATA_STORE[file_id] = {
                "raw_dataframe": sanitized_df,
                "raw_null_profile": raw_null_profile_list,
                "imputed_modeling_data": imputed_modeling_data,
                "file_name": filename,
                "detected_kind": detected_kind,
                "detected_format": detected_format,
            }

            row_count = len(sanitized_df)
            column_count = len(sanitized_df.columns)
            mem_usage = int(sanitized_df.memory_usage(deep=True).sum())

            # Infer column types for column descriptors
            inferred_types = {
                item["name"]: item["inferredType"]
                for item in infer_column_types(sanitized_df)
            }
            columns = [
                ColumnDescriptor(
                    name=col_name,
                    inferredType=inferred_types.get(col_name, "text"),
                    nullCount=p.nullCount if p.nullCount is not None else 0,
                    nullPercentage=p.nullPercentage,
                )
                for col_name, p in zip(sanitized_df.columns, raw_null_profile_list)
            ]

            # Populate raw null profile dictionary (for UI reporting and warnings)
            raw_null_profile_payload = {
                (p.columnName or str(col)): {
                    "nullCount": p.nullCount if p.nullCount is not None else 0,
                    "nullPercentage": p.nullPercentage if p.nullPercentage is not None else 0.0,
                    "totalRows": p.totalRows if p.totalRows is not None else row_count,
                }
                for col, p in zip(sanitized_df.columns, raw_null_profile_list)
            }

        # 5. For document: parse_document
        else:
            try:
                doc_result = parse_document(file_bytes, ext)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to parse document file '{filename}': {str(exc)}",
                )

            doc_text = doc_result.get("raw_text", "")
            page_count = doc_result.get("page_or_section_count", 1)

            DATA_STORE[file_id] = {
                "raw_text": doc_text,
                "doc_result": doc_result,
                "file_name": filename,
                "detected_kind": detected_kind,
                "detected_format": detected_format,
            }

            row_count = page_count
            column_count = None
            columns = None
            raw_null_profile_payload = None
            mem_usage = len(doc_text.encode("utf-8"))

        # 7. Return an UploadResponse with the raw null profile populated — not imputed data
        return UploadResponse(
            fileId=file_id,
            fileName=filename,
            fileSizeBytes=len(file_bytes),
            detectedKind=detected_kind,
            detectedFormat=detected_format,
            rowCount=row_count,
            columnCount=column_count,
            columns=columns,
            rawNullProfile=raw_null_profile_payload,
            memoryUsageBytes=mem_usage,
        )
