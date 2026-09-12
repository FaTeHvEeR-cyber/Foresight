"""Unit tests for backend/src/parsers/tabular_parser.py."""

import io
import pytest
import numpy as np
import pandas as pd

from src.models import RawNullProfile
from src.parsers.tabular_parser import (
    compute_raw_null_profile,
    downcast_numeric_columns,
    infer_column_types,
    parse_tabular,
)


@pytest.fixture
def sample_data():
    return {
        "id": [1, 2, 3, 4, 5],
        "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
        "score": [95.5, 82.0, 78.5, 91.0, 88.5],
        "active": [True, False, True, True, False],
        "created_at": ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"],
    }


def test_parse_tabular_csv(sample_data):
    df_orig = pd.DataFrame(sample_data)
    csv_bytes = df_orig.to_csv(index=False).encode("utf-8")

    df_parsed = parse_tabular(csv_bytes, "csv")
    assert len(df_parsed) == 5
    assert list(df_parsed.columns) == list(df_orig.columns)
    assert df_parsed["id"].tolist() == [1, 2, 3, 4, 5]


def test_parse_tabular_tsv(sample_data):
    df_orig = pd.DataFrame(sample_data)
    tsv_bytes = df_orig.to_csv(index=False, sep="\t").encode("utf-8")

    df_parsed = parse_tabular(tsv_bytes, "tsv")
    assert len(df_parsed) == 5
    assert list(df_parsed.columns) == list(df_orig.columns)


def test_parse_tabular_xlsx(sample_data):
    df_orig = pd.DataFrame(sample_data)
    bio = io.BytesIO()
    df_orig.to_excel(bio, index=False, engine="openpyxl")
    xlsx_bytes = bio.getvalue()

    df_parsed = parse_tabular(xlsx_bytes, "xlsx")
    assert len(df_parsed) == 5
    assert list(df_parsed.columns) == list(df_orig.columns)


def test_parse_tabular_parquet(sample_data):
    df_orig = pd.DataFrame(sample_data)
    bio = io.BytesIO()
    df_orig.to_parquet(bio, index=False)
    parquet_bytes = bio.getvalue()

    df_parsed = parse_tabular(parquet_bytes, "parquet")
    assert len(df_parsed) == 5
    assert list(df_parsed.columns) == list(df_orig.columns)


def test_parse_tabular_unsupported_format():
    with pytest.raises(ValueError, match="Unsupported tabular extension"):
        parse_tabular(b"dummy,content", "docx")


def test_parse_tabular_empty_bytes():
    with pytest.raises(ValueError, match="Cannot parse empty"):
        parse_tabular(b"", "csv")


def test_downcasting_float64_to_float32():
    df = pd.DataFrame({
        "f64": pd.Series([1.5, 2.5, 3.5, np.nan], dtype="float64"),
    })
    assert df["f64"].dtype == "float64"

    downcasted = downcast_numeric_columns(df)
    assert downcasted["f64"].dtype == np.float32
    # Verify values preserved
    assert np.isclose(downcasted["f64"].iloc[0], 1.5)
    assert pd.isna(downcasted["f64"].iloc[3])


def test_downcasting_int64_to_int16_and_int32():
    df = pd.DataFrame({
        "small_int": pd.Series([10, 20, 300, -50], dtype="int64"),
        "medium_int": pd.Series([40000, 50000, 60000, 45000], dtype="int64"),
        "large_int": pd.Series([3000000000, 4000000000, 5000000000, 6000000000], dtype="int64"),
    })
    assert df["small_int"].dtype == "int64"
    assert df["medium_int"].dtype == "int64"
    assert df["large_int"].dtype == "int64"

    downcasted = downcast_numeric_columns(df)
    assert downcasted["small_int"].dtype == np.int16
    assert downcasted["medium_int"].dtype == np.int32
    assert downcasted["large_int"].dtype == "int64"


def test_downcasting_on_ingestion():
    csv_content = b"id,val,large\n1,1.5,50000\n2,2.5,60000\n"
    df = parse_tabular(csv_content, "csv")

    assert df["id"].dtype == np.int16
    assert df["val"].dtype == np.float32
    assert df["large"].dtype == np.int32


def test_infer_column_types():
    df = pd.DataFrame({
        "num_col": [1.1, 2.2, 3.3],
        "int_col": [10, 20, 30],
        "cat_col": ["A", "B", "A"],
        "date_col": pd.date_range("2025-01-01", periods=3),
        "text_col": ["Long sentence one.", "Another distinct long text entry.", "A third unique description."],
        "bool_col": [True, False, True],
        "binary_int_col": [0, 1, 0],
        "bool_str_col": ["yes", "no", "yes"],
    })

    inferred = infer_column_types(df)
    assert isinstance(inferred, list)
    assert len(inferred) == 8

    mapping = {item["name"]: item["inferredType"] for item in inferred}
    assert mapping["num_col"] == "numeric"
    assert mapping["int_col"] == "numeric"
    assert mapping["cat_col"] == "categorical"
    assert mapping["date_col"] == "datetime"
    assert mapping["text_col"] == "text"
    assert mapping["bool_col"] == "boolean"
    assert mapping["binary_int_col"] == "boolean"
    assert mapping["bool_str_col"] == "boolean"


def test_compute_raw_null_profile():
    df = pd.DataFrame({
        "age": [25, None, 30, None, 50],             # 2 / 5 nulls = 40.0%
        "salary": [50000.0, 60000.0, None, 80000.0, 90000.0],  # 1 / 5 nulls = 20.0%
        "dept": ["Eng", "HR", "Sales", "Eng", "HR"], # 0 / 5 nulls = 0.0%
        "all_null": [None, None, None, None, None],  # 5 / 5 nulls = 100.0%
    })

    profiles = compute_raw_null_profile(df)
    assert isinstance(profiles, list)
    assert len(profiles) == 4
    assert all(isinstance(p, RawNullProfile) for p in profiles)

    prof_map = {p.columnName: p for p in profiles}

    assert prof_map["age"].nullCount == 2
    assert prof_map["age"].nullPercentage == 40.0
    assert prof_map["age"].totalRows == 5

    assert prof_map["salary"].nullCount == 1
    assert prof_map["salary"].nullPercentage == 20.0
    assert prof_map["salary"].totalRows == 5

    assert prof_map["dept"].nullCount == 0
    assert prof_map["dept"].nullPercentage == 0.0
    assert prof_map["dept"].totalRows == 5

    assert prof_map["all_null"].nullCount == 5
    assert prof_map["all_null"].nullPercentage == 100.0
    assert prof_map["all_null"].totalRows == 5


def test_no_imputation_in_tabular_parser():
    """Verify that no imputation occurs in tabular_parser, retaining all raw nulls."""
    df = pd.DataFrame({
        "numeric_nulls": [1.0, None, 3.0, None],
        "cat_nulls": ["A", None, "B", None],
    })

    profiles = compute_raw_null_profile(df)
    assert len(profiles) == 2

    # Original DataFrame must retain raw nulls untouched
    assert df["numeric_nulls"].isna().sum() == 2
    assert df["cat_nulls"].isna().sum() == 2
    assert pd.isna(df["numeric_nulls"].iloc[1])
    assert pd.isna(df["numeric_nulls"].iloc[3])
