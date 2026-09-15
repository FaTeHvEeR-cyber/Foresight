"""Ingestion and security gatekeeper router."""

import uuid
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.config import settings
from app.models.schemas import UploadResponse
from app.services.parsers import parse_document_file, parse_tabular_file
from app.services.preprocessor import create_imputed_modeling_data
from app.services.profiler import compute_memory_usage, profile_dataframe
from app.services.session_store import IngestedSession, session_store
from app.services.validator import (
    FileValidationError,
    validate_file_size,
    validate_file_type_and_signatures,
)

router = APIRouter(prefix="/api", tags=["ingestion"])

CHUNK_SIZE = 1024 * 1024  # 1MB chunks for streaming read


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)) -> UploadResponse:
    """
    Ingestion endpoint:
    - Enforces 25MB file size limit during streaming
    - Verifies MIME types and magic bytes (rejects invalid/spoofed files)
    - Extracts raw null profile without mutating original data
    - Produces imputed modeling data (median imputation + missing indicators)
    - Stores session in-memory (zero persisted disk storage)
    - Returns UploadResponse conforming to REST data contracts
    """
    filename = file.filename or "unknown"

    # 1. Stream reading with cumulative 25MB guardrail check
    buffer = bytearray()
    while chunk := await file.read(CHUNK_SIZE):
        buffer.extend(chunk)
        if len(buffer) > settings.MAX_FILE_SIZE_BYTES:
            max_mb = settings.MAX_FILE_SIZE_BYTES / (1024 * 1024)
            file_mb = len(buffer) / (1024 * 1024)
            raise FileValidationError(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds the 25MB limit ({file_mb:.2f} MB uploaded, max is {max_mb:.0f} MB)."
            )

    content = bytes(buffer)
    validate_file_size(len(content))

    # 2. Security validation: Extension, MIME, & Magic-byte inspection
    detected_kind, detected_format = validate_file_type_and_signatures(
        filename, content, file.content_type
    )

    file_id = f"f_{uuid.uuid4().hex[:10]}"
    file_size_bytes = len(content)

    if detected_kind == "tabular":
        # 3. Parse tabular dataset into raw DataFrame
        df = parse_tabular_file(content, detected_format)

        # Output 1: RAW null profile (never mutated by imputation)
        columns, raw_null_profile = profile_dataframe(df)

        # Output 2: Clean imputed modeling dataset for Ridge, K-Means, PCA
        modeling_df, indicator_cols = create_imputed_modeling_data(df)

        memory_usage_bytes = compute_memory_usage(df)

        # Store in-memory session (ephemeral)
        session = IngestedSession(
            file_id=file_id,
            file_name=filename,
            file_size_bytes=file_size_bytes,
            detected_kind="tabular",
            detected_format=detected_format,
            raw_dataframe=df,
            raw_null_profile=raw_null_profile,
            imputed_modeling_data=modeling_df,
        )
        session_store.save_session(session)

        return UploadResponse(
            file_id=file_id,
            file_name=filename,
            file_size_bytes=file_size_bytes,
            detected_kind="tabular",
            detected_format=detected_format,
            row_count=len(df),
            column_count=len(df.columns),
            columns=columns,
            raw_null_profile=raw_null_profile,
            memory_usage_bytes=memory_usage_bytes,
        )

    else:
        # Document parsing (PDF, DOCX, TXT, MD)
        doc_text = parse_document_file(content, detected_format)
        memory_usage_bytes = len(content) * 2

        session = IngestedSession(
            file_id=file_id,
            file_name=filename,
            file_size_bytes=file_size_bytes,
            detected_kind="document",
            detected_format=detected_format,
            document_text=doc_text,
        )
        session_store.save_session(session)

        # Count lines or pages
        row_count = len(doc_text.splitlines()) if doc_text else 1

        return UploadResponse(
            file_id=file_id,
            file_name=filename,
            file_size_bytes=file_size_bytes,
            detected_kind="document",
            detected_format=detected_format,
            row_count=row_count,
            column_count=None,
            columns=None,
            raw_null_profile=None,
            memory_usage_bytes=memory_usage_bytes,
        )
