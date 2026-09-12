"""Tests for Ingestion Profiler: Raw null counts, percentages, and type inference."""

import pandas as pd
from app.services.profiler import infer_column_type, profile_dataframe


def test_raw_null_profile_accuracy_and_retention():
    """Verify exact null counts and null percentages are computed and retained."""
    df = pd.DataFrame(
        {
            "age": [25, None, 30, None, 50],           # 2 nulls out of 5 = 40.0%
            "salary": [50000.0, 60000.0, None, 80000.0, 90000.0],  # 1 null out of 5 = 20.0%
            "department": ["Eng", "HR", "Sales", "Eng", "HR"],     # 0 nulls = 0.0%
            "all_null": [None, None, None, None, None],             # 5 nulls = 100.0%
        }
    )

    columns, raw_profile = profile_dataframe(df)

    assert len(columns) == 4
    assert len(raw_profile) == 4

    # Verify column descriptors
    col_map = {c.name: c for c in columns}
    assert col_map["age"].nullCount == 2
    assert col_map["age"].nullPercentage == 40.0
    assert col_map["age"].inferredType == "numeric"

    assert col_map["salary"].nullCount == 1
    assert col_map["salary"].nullPercentage == 20.0
    assert col_map["salary"].inferredType == "numeric"

    assert col_map["department"].nullCount == 0
    assert col_map["department"].nullPercentage == 0.0
    assert col_map["department"].inferredType == "categorical"

    assert col_map["all_null"].nullCount == 5
    assert col_map["all_null"].nullPercentage == 100.0

    # Verify raw null profile dictionary (for UI warnings / metrics)
    assert raw_profile["age"].nullCount == 2
    assert raw_profile["age"].nullPercentage == 40.0
    assert raw_profile["age"].totalRows == 5

    assert raw_profile["salary"].nullCount == 1
    assert raw_profile["salary"].nullPercentage == 20.0

    assert raw_profile["department"].nullCount == 0
    assert raw_profile["department"].nullPercentage == 0.0

    # Verify df was NOT mutated
    assert df["age"].isna().sum() == 2
    assert df["salary"].isna().sum() == 1


def test_inferred_types():
    """Verify type inference across boolean, numeric, datetime, categorical, and text."""
    n = 50
    df = pd.DataFrame(
        {
            "bool_col": [True if i % 2 == 0 else False for i in range(n)],
            "num_col": [float(i) * 1.1 for i in range(n)],
            "int_col": [i * 10 for i in range(n)],
            "date_col": pd.date_range("2025-01-01", periods=n, freq="D"),
            "cat_col": ["Category_" + str(i % 3) for i in range(n)],  # Low cardinality: 3 categories
            "text_col": ["Unique text passage with detailed description " + str(i) for i in range(n)],
        }
    )

    assert infer_column_type(df["bool_col"]) == "boolean"
    assert infer_column_type(df["num_col"]) == "numeric"
    assert infer_column_type(df["int_col"]) == "numeric"
    assert infer_column_type(df["date_col"]) == "datetime"
    assert infer_column_type(df["cat_col"]) == "categorical"
    assert infer_column_type(df["text_col"]) == "text"
