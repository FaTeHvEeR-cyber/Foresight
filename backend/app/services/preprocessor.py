"""Modeling dataset preprocessor: median imputation + missing-indicator encoding.

Produces clean, NaN-free modeling data suitable for Ridge regression, K-Means,
and PCA while preserving missingness signals through indicator columns.
Guarantees the raw DataFrame is never mutated.
"""

from typing import Dict, List, Tuple, cast
import pandas as pd

from app.models.schemas import ImputationSummary


def create_imputed_modeling_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """
    Produce clean, imputed modeling data from raw DataFrame.
    
    Operations:
    1. Makes a deep copy of raw df to preserve raw null profile intact.
    2. Identifies numeric columns with NaNs:
       - Adds float indicator column `{col}_isna` (1.0 for missing, 0.0 for present).
       - Imputes missing values with column median (fallback to 0.0 if all NaN).
    3. Identifies categorical/object columns with NaNs:
       - Fills missing values with 'missing'.
    
    Returns:
    - imputed_df: DataFrame ready for Ridge, K-Means, PCA with zero NaNs in features.
    - indicator_cols: List of indicator column names created.
    """
    imputed_df = df.copy()
    indicator_cols: List[str] = []

    # Numeric columns
    numeric_cols = [
        col for col in imputed_df.columns
        if pd.api.types.is_numeric_dtype(imputed_df[col]) and not pd.api.types.is_bool_dtype(imputed_df[col])
    ]

    for col in numeric_cols:
        col_str = f"{col}"
        series = imputed_df[col]

        if bool(series.isna().any()):
            # 1. Indicator column: {col}_isna (using float for scikit-learn compliance)
            indicator_name = f"{col_str}_isna"
            imputed_df[indicator_name] = series.isna().astype(float)
            indicator_cols.append(indicator_name)

            # 2. Median imputation
            median_raw = series.median()
            median_val = float(cast(float, median_raw)) if not bool(pd.isna(median_raw)) else 0.0

            imputed_df[col] = series.fillna(median_val)

    # Categorical columns
    non_numeric_cols = [
        col for col in imputed_df.columns
        if col not in numeric_cols and col not in indicator_cols
    ]
    for col in non_numeric_cols:
        if bool(imputed_df[col].isna().any()):
            imputed_df[col] = imputed_df[col].fillna("missing")

    return imputed_df, indicator_cols


def prepare_modeling_dataset(df: pd.DataFrame) -> Tuple[pd.DataFrame, ImputationSummary]:
    """Extended wrapper returning imputed DataFrame and ImputationSummary model."""
    imputed_df, indicator_cols = create_imputed_modeling_data(df)
    
    imputed_numeric_cols = [c.replace("_isna", "") for c in indicator_cols]
    median_values: Dict[str, float] = {}
    for col in imputed_numeric_cols:
        med_val = df[col].median()
        median_values[col] = float(cast(float, med_val)) if not bool(pd.isna(med_val)) else 0.0

    summary = ImputationSummary(
        imputed_numeric_columns=imputed_numeric_cols,
        added_indicator_columns=indicator_cols,
        median_values=median_values,
    )
    return imputed_df, summary
