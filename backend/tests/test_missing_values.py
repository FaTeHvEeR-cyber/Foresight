"""Test suite for Missing Values Implementation Decision:

1. Ingestion/profiling layer separately retains and reports RAW null counts/percentages
   per column for UI display and data-quality warnings.
2. Modeling/feature pipeline produces imputed modeling data using median imputation +
   missing-indicator encoding so Ridge, K-Means, and PCA don't choke on NaNs.
3. Raw null profile and imputed modeling data are two distinct outputs; raw data is never mutated.
"""

import io
import numpy as np
import pandas as pd
from src.parsers.imputation import impute_for_modeling
from src.parsers.tabular_parser import compute_raw_null_profile, infer_column_types


def test_dual_output_separation_and_immutability():
    """Test that profiling extracts raw null counts/percentages and that

    preprocessor produces clean imputed data without mutating the raw DataFrame.
    """
    raw_df = pd.DataFrame({
        "sales": [100.0, np.nan, 300.0, np.nan, 500.0],
        "cost": [50.0, 60.0, 70.0, 80.0, 90.0],
        "region": ["North", np.nan, "South", "East", "West"],
    })

    # 1. Profile raw DataFrame
    raw_profile_list = compute_raw_null_profile(raw_df)
    inferred_types = {item["name"]: item["inferredType"] for item in infer_column_types(raw_df)}
    raw_profile = {p.columnName: p for p in raw_profile_list}

    # Verify Raw Profile retains exact null counts and percentages
    # sales has [100.0, NaN, 300.0, NaN, 500.0] -> 2 NaNs out of 5 = 40.0%
    sales_profile = raw_profile["sales"]
    assert sales_profile.nullCount == 2
    assert sales_profile.nullPercentage == 40.0
    assert sales_profile.totalRows == 5

    # cost has [50.0, 60.0, 70.0, 80.0, 90.0] -> 0 NaNs = 0.0%
    cost_profile = raw_profile["cost"]
    assert cost_profile.nullCount == 0
    assert cost_profile.nullPercentage == 0.0

    # region has ["North", NaN, "South", "East", "West"] -> 1 NaN = 20.0%
    region_profile = raw_profile["region"]
    assert region_profile.nullCount == 1
    assert region_profile.nullPercentage == 20.0

    # Verify column descriptors match
    assert inferred_types["sales"] == "numeric"
    assert inferred_types["cost"] == "numeric"
    assert inferred_types["region"] in ("categorical", "text")

    # 2. Run feature preprocessor for modeling pipeline
    imputed_df = impute_for_modeling(raw_df)

    # 3. VERIFY IMMUTABILITY: raw_df must still have NaNs!
    assert raw_df["sales"].isna().sum() == 2, "Raw DataFrame was mutated by imputation!"
    assert raw_df["region"].isna().sum() == 1, "Raw DataFrame was mutated by imputation!"
    assert "sales_was_missing" not in raw_df.columns, "Raw DataFrame columns were modified!"

    # 4. Verify Imputed Modeling Data
    # Zero NaNs in numeric columns
    assert imputed_df["sales"].isna().sum() == 0
    assert imputed_df["cost"].isna().sum() == 0

    # Median of [100.0, 300.0, 500.0] is 300.0
    expected_sales_imputed = [100.0, 300.0, 300.0, 300.0, 500.0]
    assert np.allclose(imputed_df["sales"].tolist(), expected_sales_imputed)

    # Missing indicator column created
    assert "sales_was_missing" in imputed_df.columns
    assert list(imputed_df["sales_was_missing"]) == [False, True, False, True, False]

    # Categorical imputation
    assert imputed_df["region"].isna().sum() == 0
    assert imputed_df["region"].iloc[1] == "missing"


def test_upload_endpoint_returns_raw_null_profile(client, sample_csv_bytes):
    """Verify the /api/v1/upload endpoint returns the raw null profile for UI display."""
    files = {"file": ("data_with_nulls.csv", io.BytesIO(sample_csv_bytes), "text/csv")}
    response = client.post("/api/v1/upload", files=files)
    assert response.status_code == 200

    data = response.json()

    # 1. Verify Raw Null Profile in response
    assert "rawNullProfile" in data
    raw_profile = data["rawNullProfile"]
    assert "age" in raw_profile
    assert raw_profile["age"]["nullCount"] == 1
    assert raw_profile["age"]["totalRows"] == 5

    # 2. Verify Columns contain raw null metrics
    cols = data["columns"]
    age_col = next(c for c in cols if c["name"] == "age")
    assert age_col["nullCount"] == 1
    assert age_col["nullPercentage"] == 20.0
