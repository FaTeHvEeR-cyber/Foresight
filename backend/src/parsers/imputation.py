"""Modeling dataset imputation pipeline: median imputation and missing-indicator encoding.

IMPORTANT ARCHITECTURAL SEPARATION:
This module's output (from impute_for_modeling) is strictly for the downstream modeling
pipeline (Ridge regression, K-Means clustering, PCA, etc.) so estimators never encounter NaNs.
It must NOT be used as the source of null-count reporting.
Null-count reporting comes exclusively from compute_raw_null_profile() in tabular_parser.py,
which is computed on the raw DataFrame BEFORE this imputation function runs.
"""

from typing import cast

import numpy as np
import pandas as pd


def impute_for_modeling(df: pd.DataFrame) -> pd.DataFrame:
    """Produce clean, imputed modeling data from a raw DataFrame.

    Applies median imputation to numeric columns and adds a '{column}_was_missing'
    boolean indicator column for each column that had any nulls, ensuring downstream
    modeling algorithms (Ridge, K-Means, PCA) never encounter NaNs.

    CRITICAL USAGE NOTE:
    This function's OUTPUT is for the modeling pipeline only. It must NOT be used
    as the source of null-count reporting — that comes from compute_raw_null_profile()
    in tabular_parser.py, computed BEFORE this function runs.

    Args:
        df: Raw pandas DataFrame. The input DataFrame is never mutated in-place.

    Returns:
        pd.DataFrame: Imputed DataFrame copy with zero NaNs in numeric columns and
            '{column}_was_missing' boolean indicator columns for any columns with nulls.
    """
    # CRITICAL ARCHITECTURAL GUARANTEE:
    # This function's OUTPUT is for the modeling pipeline only.
    # It must NOT be used as the source of null-count reporting — that comes from
    # compute_raw_null_profile() in tabular_parser.py, computed BEFORE this
    # function runs. Never conflate imputed values with raw null reporting!

    if df.empty:
        return df.copy()

    imputed_df = df.copy()
    original_cols = list(imputed_df.columns)

    # 1. Identify numeric columns (excluding boolean dtypes)
    numeric_cols = [
        col for col in original_cols
        if pd.api.types.is_numeric_dtype(imputed_df[col]) and not pd.api.types.is_bool_dtype(imputed_df[col])
    ]

    # 2. Impute numeric columns with median and record missing indicators
    for col in numeric_cols:
        series = imputed_df[col]
        if bool(series.isna().any()):
            # Boolean indicator column: True where value was missing, False otherwise
            imputed_df[f"{col}_was_missing"] = series.isna()

            # Calculate column median with 0.0 fallback if column is entirely NaN
            median_val = series.median()
            if pd.isna(median_val):  # type: ignore[reportGeneralTypeIssues]
                median_val = 0.0
            else:
                median_val = float(median_val)

            # Preserve float32 or cast if downcasted
            if series.dtype == np.float32:
                imputed_df[col] = series.fillna(np.float32(median_val))
            else:
                imputed_df[col] = series.fillna(median_val)

    # 3. Handle non-numeric columns with nulls: add indicator and fillna
    non_numeric_cols = [col for col in original_cols if col not in numeric_cols]
    for col in non_numeric_cols:
        series = imputed_df[col]
        if bool(series.isna().any()):
            imputed_df[f"{col}_was_missing"] = series.isna()

            # Categorical handling
            if isinstance(series.dtype, pd.CategoricalDtype):
                if "missing" not in series.cat.categories:
                    series = series.cat.add_categories(["missing"])
                imputed_df[col] = series.fillna("missing")
            elif pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
                imputed_df[col] = series.fillna("missing")

    return imputed_df
