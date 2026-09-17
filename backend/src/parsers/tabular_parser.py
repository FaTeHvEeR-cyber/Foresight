"""In-memory tabular parser and raw null profiler for Foresight backend.

Provides parsing for tabular formats (csv, tsv, xlsx, xls, parquet) via pandas/openpyxl
reading exclusively from io.BytesIO without writing to disk.
Downcasts numeric columns on ingestion to minimize memory footprint (per spec §5.2).
Computes raw null profiles before any downstream imputation logic is applied.
"""

import io
from typing import Literal
import warnings
import numpy as np
import pandas as pd

from src.models import ColumnNullMetric, RawNullProfile


InferredType = Literal["numeric", "categorical", "datetime", "text", "boolean"]


def downcast_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Downcast numeric columns to cut memory footprint per spec §5.2.

    Conversions:
    - float64 -> float32 where safe (values fit in float32 range without overflow)
    - int64 -> int16 or int32 where safe (values fit in int16 or int32 range)

    Args:
        df: Input DataFrame.

    Returns:
        pd.DataFrame: DataFrame with downcasted numeric columns.
    """
    df_downcasted = df.copy()

    for col in df_downcasted.columns:
        series = df_downcasted[col]
        dtype = series.dtype

        # Float downcasting: float64 -> float32
        if dtype == "float64":
            c_min = series.min()
            c_max = series.max()
            f32_min = np.finfo(np.float32).min
            f32_max = np.finfo(np.float32).max
            if bool(pd.isna(c_min)):
                df_downcasted[col] = series.astype(np.float32)
            elif c_min >= f32_min and c_max <= f32_max:
                converted = series.astype(np.float32)
                # Ensure casting didn't turn finite values into inf
                if np.isinf(converted).sum() == np.isinf(series).sum():
                    df_downcasted[col] = converted

        # Integer downcasting: int64 -> int16 or int32
        elif dtype == "int64":
            c_min = series.min()
            c_max = series.max()
            i16_min = np.iinfo(np.int16).min
            i16_max = np.iinfo(np.int16).max
            i32_min = np.iinfo(np.int32).min
            i32_max = np.iinfo(np.int32).max

            if bool(pd.isna(c_min)):
                df_downcasted[col] = series.astype(np.int16)
            elif c_min >= i16_min and c_max <= i16_max:
                df_downcasted[col] = series.astype(np.int16)
            elif c_min >= i32_min and c_max <= i32_max:
                df_downcasted[col] = series.astype(np.int32)

    return df_downcasted


def parse_tabular(file_bytes: bytes, extension: str) -> pd.DataFrame:
    """Parse raw byte content into a pandas DataFrame in memory without touching disk.

    Supports csv, tsv, xlsx, xls, parquet via pandas and openpyxl.
    Downcasts numeric columns on ingestion per spec §5.2.

    Args:
        file_bytes: Raw bytes of the uploaded tabular file.
        extension: File extension (e.g. 'csv', '.csv', 'tsv', 'xlsx', 'xls', 'parquet').

    Returns:
        pd.DataFrame: Ingested and memory-optimized DataFrame.

    Raises:
        ValueError: If file_bytes is empty or extension is unsupported.
    """
    if not file_bytes:
        raise ValueError("Cannot parse empty file content")

    ext = extension.strip().lower().lstrip(".")
    bio = io.BytesIO(file_bytes)

    if ext == "csv":
        try:
            df = pd.read_csv(bio)
        except Exception:
            bio.seek(0)
            df = pd.read_csv(bio, sep=None, engine="python")
    elif ext == "tsv":
        df = pd.read_csv(bio, sep="\t")
    elif ext in ("xlsx", "xls"):
        try:
            df = pd.read_excel(bio, engine="openpyxl")
        except Exception:
            bio.seek(0)
            df = pd.read_excel(bio)
    elif ext == "parquet":
        df = pd.read_parquet(bio)
    else:
        raise ValueError(f"Unsupported tabular extension: {extension}")

    # Downcast numeric columns on ingestion to cut memory footprint (spec §5.2)
    return downcast_numeric_columns(df)


def infer_column_type(series: pd.Series) -> InferredType:
    """Infer column type as one of: numeric, categorical, datetime, text, boolean."""
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
        unique_vals = set(non_nulls.unique())
        if unique_vals.issubset({0, 1}) and len(unique_vals) <= 2 and not pd.api.types.is_float_dtype(series):
            return "boolean"
        return "numeric"

    # 4. String / Object sniffing
    sample = non_nulls.head(50)
    lower_sample = sample.astype(str).str.lower().str.strip()

    # Boolean strings
    if set(lower_sample).issubset({"true", "false", "t", "f", "yes", "no"}):
        return "boolean"

    # Datetime string parsing
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
            if parsed.notna().sum() > len(sample) * 0.8:
                return "datetime"
    except Exception:
        pass

    # Categorical vs Text
    if isinstance(series.dtype, pd.CategoricalDtype):
        return "categorical"

    str_series = non_nulls.astype(str)
    mean_len = str_series.str.len().mean()
    num_unique = non_nulls.nunique()
    total_count = len(non_nulls)
    unique_ratio = (num_unique / total_count) if total_count > 0 else 0.0

    # Long text strings or multi-word high-cardinality entries are text
    if mean_len > 50 or (mean_len > 20 and unique_ratio > 0.5 and str_series.str.contains(" ").any()):
        return "text"

    if num_unique <= 20 or unique_ratio < 0.1:
        return "categorical"

    return "text"


def infer_column_types(df: pd.DataFrame) -> list[dict]:
    """Infer column types for each column in the DataFrame.

    Returns:
        list[dict]: A list of dicts with {"name": str, "inferredType": "numeric"|"categorical"|"datetime"|"text"|"boolean"}
        for each column.
    """
    result = []
    for col in df.columns:
        result.append({
            "name": f"{col}",
            "inferredType": infer_column_type(pd.Series(df[col])),
        })
    return result


def compute_raw_null_profile(df: pd.DataFrame) -> list[RawNullProfile]:
    """Compute raw null profile reporting un-imputed null counts and percentages per column.

    Imported from src.models (RawNullProfile).
    Must be computed BEFORE any downstream imputation happens.
    Contains no imputation logic — only parses and profiles raw data.

    Args:
        df: Raw pandas DataFrame before any imputation.

    Returns:
        list[RawNullProfile]: Un-imputed null profile metrics per column.
    """
    total_rows = len(df)
    profiles: list[RawNullProfile] = []

    for col in df.columns:
        col_name = f"{col}"
        series = pd.Series(df[col])
        null_count = int(series.isna().sum())
        null_pct = round((null_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0

        metric = ColumnNullMetric(
            columnName=col_name,
            nullCount=null_count,
            nullPercentage=null_pct,
        )
        profile = RawNullProfile(
            columnName=col_name,
            nullCount=null_count,
            nullPercentage=null_pct,
            columns=[metric],
            totalRows=total_rows,
        )
        profiles.append(profile)

    return profiles
