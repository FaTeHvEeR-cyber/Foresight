"""Pydantic schemas and REST data contracts for Foresight backend."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

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


class CamelModel(BaseModel):
    """Base model with automatic camelCase serialization and dual attribute access."""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ColumnDescriptor(CamelModel):
    name: str
    inferred_type: InferredType = Field(..., alias="inferredType")
    null_count: int = Field(..., alias="nullCount")
    null_percentage: Optional[float] = Field(0.0, alias="nullPercentage")

    @property
    def nullCount(self) -> int:
        return self.null_count

    @property
    def nullPercentage(self) -> float:
        return self.null_percentage if self.null_percentage is not None else 0.0

    @property
    def inferredType(self) -> str:
        return self.inferred_type


class ColumnNullProfile(CamelModel):
    null_count: int = Field(..., alias="nullCount")
    null_percentage: float = Field(..., alias="nullPercentage")
    total_rows: int = Field(..., alias="totalRows")

    @property
    def nullCount(self) -> int:
        return self.null_count

    @property
    def nullPercentage(self) -> float:
        return self.null_percentage

    @property
    def totalRows(self) -> int:
        return self.total_rows


class ImputationSummary(CamelModel):
    imputed_numeric_columns: List[str] = Field(default_factory=list)
    added_indicator_columns: List[str] = Field(default_factory=list)
    median_values: Dict[str, float] = Field(default_factory=dict)


class UploadResponse(CamelModel):
    file_id: str = Field(..., alias="fileId")
    file_name: str = Field(..., alias="fileName")
    file_size_bytes: int = Field(..., alias="fileSizeBytes")
    detected_kind: DetectedFileKind = Field(..., alias="detectedKind")
    detected_format: DetectedFormat = Field(..., alias="detectedFormat")
    row_count: Optional[int] = Field(None, alias="rowCount")
    column_count: Optional[int] = Field(None, alias="columnCount")
    columns: Optional[List[ColumnDescriptor]] = None
    raw_null_profile: Optional[Dict[str, ColumnNullProfile]] = Field(None, alias="rawNullProfile")
    memory_usage_bytes: int = Field(..., alias="memoryUsageBytes")
    imputation_summary: Optional[ImputationSummary] = Field(None, alias="imputationSummary")
    data_quality_warnings: List[str] = Field(default_factory=list, alias="dataQualityWarnings")


class HealthResponse(CamelModel):
    status: str
    app_name: str = Field(..., alias="appName")
    version: str
    max_file_size_bytes: int = Field(..., alias="maxFileSizeBytes")
    rate_limiting_enabled: bool = Field(..., alias="rateLimitingEnabled")
    supported_formats: List[str] = Field(..., alias="supportedFormats")
