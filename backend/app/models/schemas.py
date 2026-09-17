"""Pydantic schemas and REST data contracts for Foresight backend."""

from typing import Dict, List, Literal, Optional
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
    inferred_type: InferredType
    null_count: int
    null_percentage: Optional[float] = 0.0

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
    null_count: int
    null_percentage: float
    total_rows: int

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
    file_id: str
    file_name: str
    file_size_bytes: int
    detected_kind: DetectedFileKind
    detected_format: DetectedFormat
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    columns: Optional[List[ColumnDescriptor]] = None
    raw_null_profile: Optional[Dict[str, ColumnNullProfile]] = None
    memory_usage_bytes: int
    imputation_summary: Optional[ImputationSummary] = None
    data_quality_warnings: List[str] = Field(default_factory=list)


class HealthResponse(CamelModel):
    status: str
    app_name: str
    version: str
    max_file_size_bytes: int
    rate_limiting_enabled: bool
    supported_formats: List[str]
