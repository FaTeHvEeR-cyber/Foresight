"""Ingestion and profiling service.

Retains and reports RAW null counts, percentages, and data quality warnings
per column for UI display. Does NOT mutate raw input data.
"""

from typing import Dict, List, Tuple
import pandas as pd

from app.models.schemas import (
    ColumnDescriptor,
    ColumnNullProfile,
    InferredType,
)


def infer_column_type(series: pd.Series) -> InferredType:
    """Infer column type (numeric, categorical, datetime, text, boolean)."""
    # 1. Boolean check
    if pd.api.types.is_bool_dtype(series):
        return "boolean"

    non_nulls = series.dropna()
    if non_nulls.empty:
        return "text"

    # 2. Datetime check
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"

    # 3. Numeric check
    if pd.api.types.is_numeric_dtype(series):
        # If numeric but only contains {0, 1} and is boolean flag
        unique_vals = set(non_nulls.unique())
        if unique_vals.issubset({0, 1}) and len(unique_vals) <= 2 and not pd.api.types.is_float_dtype(series):
            return "boolean"
        return "numeric"

    # 4. String / Object sniffing
    sample = non_nulls.head(50)
    lower_sample = sample.astype(str).str.lower().str.strip()
    if set(lower_sample).issubset({"true", "false", "t", "f", "yes", "no"}):
        return "boolean"

    try:
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        if parsed.notna().sum() > len(sample) * 0.8:
            return "datetime"
    except Exception:
        pass

    num_unique = non_nulls.nunique()
    total_count = len(non_nulls)
    if num_unique <= 20 or (total_count > 0 and (num_unique / total_count) < 0.1):
        return "categorical"
    return "text"


def profile_dataframe(
    df: pd.DataFrame
) -> Tuple[List[ColumnDescriptor], Dict[str, ColumnNullProfile]]:
    """
    Compute raw column descriptors and raw null profile dictionary without mutating df.
    Returns:
    - columns: List[ColumnDescriptor] with name, inferredType, nullCount, nullPercentage
    - raw_null_profile: Dict[str, ColumnNullProfile] with nullCount, nullPercentage, totalRows
    """
    total_rows = len(df)
    descriptors: List[ColumnDescriptor] = []
    raw_profile: Dict[str, ColumnNullProfile] = {}

    for col in df.columns:
        col_str = f"{col}"
        series = pd.Series(df[col])
        null_count = int(series.isna().sum())
        null_pct = round((null_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0
        inferred = infer_column_type(series)

        col_profile = ColumnNullProfile(
            null_count=null_count,
            null_percentage=null_pct,
            total_rows=total_rows,
        )
        raw_profile[col_str] = col_profile

        descriptors.append(
            ColumnDescriptor(
                name=col_str,
                inferred_type=inferred,
                null_count=null_count,
                null_percentage=null_pct,
            )
        )

    return descriptors, raw_profile


def profile_tabular_dataset(
    df: pd.DataFrame
) -> Tuple[List[ColumnDescriptor], Dict[str, ColumnNullProfile], List[str]]:
    """Extended profiler returning columns, raw_profile, and data quality warnings."""
    columns, raw_profile = profile_dataframe(df)
    warnings: List[str] = []

    for col, prof in raw_profile.items():
        if prof.null_percentage == 100.0:
            warnings.append(f"Column '{col}' is completely empty (100% null values).")
        elif prof.null_percentage >= 50.0:
            warnings.append(
                f"Column '{col}' has high missingness ({prof.null_percentage}% nulls)."
            )
        elif prof.null_percentage >= 20.0:
            warnings.append(
                f"Column '{col}' has moderate missingness ({prof.null_percentage}% nulls)."
            )

    return columns, raw_profile, warnings


def compute_memory_usage(df: pd.DataFrame) -> int:
    """Compute in-memory byte usage of a DataFrame."""
    try:
        return int(df.memory_usage(deep=True).sum())
    except Exception:
        return int(df.memory_usage().sum())
