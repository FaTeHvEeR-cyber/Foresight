"""Unit tests for backend/src/parsers/imputation.py.

Verifies:
1. impute_for_modeling applies median imputation to numeric columns.
2. "{column}_was_missing" boolean indicator column is added for every column with nulls.
3. Zero NaNs remain in numeric features, allowing Ridge, KMeans, and PCA to run cleanly.
4. Immutability: original raw DataFrame is never mutated.
5. Explicit architectural separation from compute_raw_null_profile() in tabular_parser.py.
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge

from src.parsers.imputation import impute_for_modeling
from src.parsers.tabular_parser import compute_raw_null_profile


def test_impute_for_modeling_numeric_median_and_boolean_indicator():
    """Verify median imputation for numeric columns and boolean {col}_was_missing indicator."""
    raw_df = pd.DataFrame({
        # Medians: age = 30.0, salary = 75000.0
        "age": [20.0, None, 30.0, None, 40.0],
        "salary": [50000.0, 70000.0, 80000.0, None, 100000.0],
        "score": [10.0, 20.0, 30.0, 40.0, 50.0],  # No nulls
        "dept": ["Eng", None, "Sales", "Eng", "HR"],
    })

    imputed_df = impute_for_modeling(raw_df)

    # 1. Indicator columns: boolean dtype, created only for columns with nulls
    assert "age_was_missing" in imputed_df.columns
    assert "salary_was_missing" in imputed_df.columns
    assert "dept_was_missing" in imputed_df.columns
    assert "score_was_missing" not in imputed_df.columns

    assert imputed_df["age_was_missing"].dtype == bool
    assert imputed_df["salary_was_missing"].dtype == bool
    assert imputed_df["dept_was_missing"].dtype == bool

    # Verify exact boolean indicator masks
    assert imputed_df["age_was_missing"].tolist() == [False, True, False, True, False]
    assert imputed_df["salary_was_missing"].tolist() == [False, False, False, True, False]
    assert imputed_df["dept_was_missing"].tolist() == [False, True, False, False, False]

    # 2. Verify median imputation
    # Median of [20.0, 30.0, 40.0] is 30.0
    assert imputed_df["age"].tolist() == [20.0, 30.0, 30.0, 30.0, 40.0]
    assert imputed_df["age"].isna().sum() == 0

    # Median of [50000.0, 70000.0, 80000.0, 100000.0] is 75000.0
    assert imputed_df["salary"].tolist() == [50000.0, 70000.0, 80000.0, 75000.0, 100000.0]
    assert imputed_df["salary"].isna().sum() == 0

    # Score had no nulls, remains unchanged
    assert imputed_df["score"].tolist() == [10.0, 20.0, 30.0, 40.0, 50.0]

    # Categorical null filled
    assert imputed_df["dept"].iloc[1] == "missing"
    assert imputed_df["dept"].isna().sum() == 0


def test_immutability_raw_dataframe_preserved():
    """Verify raw DataFrame is not mutated in-place by imputation."""
    raw_df = pd.DataFrame({
        "sales": [100.0, np.nan, 300.0],
        "category": ["A", None, "B"],
    })

    imputed_df = impute_for_modeling(raw_df)

    # Raw DataFrame must still retain all NaNs and original columns
    assert raw_df["sales"].isna().sum() == 1
    assert raw_df["category"].isna().sum() == 1
    assert "sales_was_missing" not in raw_df.columns
    assert "category_was_missing" not in raw_df.columns

    # Imputed DataFrame has 0 NaNs
    assert imputed_df["sales"].isna().sum() == 0
    assert imputed_df["sales_was_missing"].tolist() == [False, True, False]


def test_architectural_separation_from_compute_raw_null_profile():
    """Verify that null-count reporting must be derived from compute_raw_null_profile()

    before imputation, because impute_for_modeling() intentionally has 0 nulls.
    """
    raw_df = pd.DataFrame({
        "metric_a": [1.0, None, None, 4.0, 5.0],  # 2 nulls (40%)
        "metric_b": [10.0, 20.0, 30.0, 40.0, 50.0],  # 0 nulls (0%)
    })

    # Step 1: Raw null profile computed BEFORE imputation
    profiles = compute_raw_null_profile(raw_df)
    prof_map = {p.columnName: p for p in profiles}

    assert prof_map["metric_a"].nullCount == 2
    assert prof_map["metric_a"].nullPercentage == 40.0
    assert prof_map["metric_b"].nullCount == 0
    assert prof_map["metric_b"].nullPercentage == 0.0

    # Step 2: Modeling imputation
    modeling_df = impute_for_modeling(raw_df)

    # Modeling df has zero nulls (never use modeling_df for null reporting!)
    assert modeling_df["metric_a"].isna().sum() == 0
    assert modeling_df["metric_b"].isna().sum() == 0

    # Raw df still has nulls
    assert raw_df["metric_a"].isna().sum() == 2


def test_downstream_modeling_algorithms_succeed():
    """Verify Ridge, KMeans, and PCA run without NaNs on output of impute_for_modeling."""
    np.random.seed(42)
    n_samples = 40
    data = {
        "x1": np.random.randn(n_samples),
        "x2": np.random.randn(n_samples),
        "x3": np.random.randn(n_samples),
        "target": np.random.randn(n_samples),
    }
    df = pd.DataFrame(data)

    # Introduce missingness
    df.loc[0:5, "x1"] = np.nan
    df.loc[10:18, "x2"] = np.nan

    imputed = impute_for_modeling(df)

    # Select numeric feature columns (including the was_missing indicators)
    feature_cols = [c for c in imputed.columns if c != "target"]
    assert not bool(imputed[feature_cols].isna().to_numpy().any()), "Feature matrix contains NaNs!"

    X = imputed[feature_cols].astype(float).values
    y = imputed["target"].to_numpy(dtype=float)

    # 1. Ridge regression
    ridge = Ridge()
    ridge.fit(X, y)
    preds = ridge.predict(X)
    assert len(preds) == n_samples

    # 2. KMeans clustering
    kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)  # type: ignore[arg-type]
    clusters = kmeans.fit_predict(X)
    assert len(clusters) == n_samples

    # 3. PCA decomposition
    pca = PCA(n_components=2)
    components = pca.fit_transform(X)
    assert components.shape == (n_samples, 2)


def test_all_null_numeric_column_fallback():
    """Verify all-null column gracefully defaults to 0.0 without NaN leftovers."""
    df = pd.DataFrame({
        "all_missing": [None, np.nan, None],
        "valid": [1.0, 2.0, 3.0],
    })

    imputed = impute_for_modeling(df)
    assert imputed["all_missing"].tolist() == [0.0, 0.0, 0.0]
    assert imputed["all_missing_was_missing"].tolist() == [True, True, True]
    assert imputed["all_missing"].isna().sum() == 0


def test_empty_dataframe_and_no_missing_values():
    """Verify empty DataFrame and DataFrames with 0 nulls are handled cleanly."""
    empty_df = pd.DataFrame()
    assert impute_for_modeling(empty_df).empty

    clean_df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
    imputed = impute_for_modeling(clean_df)
    assert imputed.equals(clean_df)
    assert not any("_was_missing" in c for c in imputed.columns)
