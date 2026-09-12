"""Pydantic response models mirroring frontend/types/api.ts UploadResponse exactly."""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field

DetectedFileKind = Literal["tabular", "document", "mixed"]

DetectedFormat = Literal[
    "csv",
    "tsv",
    "xlsx",
    "xls",
    "parquet",
    "pdf",
    "docx",
    "txt",
    "md",
]

InferredType = Literal["numeric", "categorical", "datetime", "text", "boolean"]


class ColumnDescriptor(BaseModel):
    name: str
    inferredType: InferredType
    nullCount: int
    nullPercentage: Optional[float] = None


class ColumnNullMetric(BaseModel):
    columnName: str
    nullCount: int
    nullPercentage: float


class RawNullProfile(BaseModel):
    """Raw null profile reporting un-imputed null counts and percentages per column.

    Kept strictly separate from any imputed data structure.
    """
    columns: List[ColumnNullMetric] = Field(default_factory=list)
    totalRows: Optional[int] = None


class UploadResponse(BaseModel):
    fileId: str
    fileName: str
    fileSizeBytes: int
    detectedKind: DetectedFileKind
    detectedFormat: DetectedFormat
    rowCount: Optional[int] = None
    columnCount: Optional[int] = None
    columns: Optional[List[ColumnDescriptor]] = None
    rawNullProfile: Optional[Union[RawNullProfile, List[ColumnNullMetric], Dict[str, Any]]] = None
    memoryUsageBytes: int
