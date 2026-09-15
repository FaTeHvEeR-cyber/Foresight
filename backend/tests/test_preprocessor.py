"""Tests for Missing Value Imputation Pipeline: Median imputation and indicator encoding."""

import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

from app.services.preprocessor import create_imputed_modeling_data


def test_median_imputation_and_indicator_encoding():
    """Verify numeric columns with NaNs get median imputation and <col>_isna indicator."""
    df = pd.DataFrame(
        {
            # Medians: age = 30.0, salary = 70000.0
            "age": [20.0, None, 30.0, None, 40.0],
            "salary": [50000.0, 70000.0, 90000.0, None, 100000.0],
            "score": [10.0, 20.0, 30.0, 40.0, 50.0],  # No nulls
            "dept": ["Eng", None, "Sales", "Eng", "HR"],
        }
    )

    imputed_df, indicator_cols = create_imputed_modeling_data(df)

    # 1. Check indicators created only for columns with missing values
    assert "age_isna" in indicator_cols
    assert "salary_isna" in indicator_cols
    assert "score_isna" not in indicator_cols

    # Verify indicator column values
    assert list(imputed_df["age_isna"]) == [0.0, 1.0, 0.0, 1.0, 0.0]
    assert list(imputed_df["salary_isna"]) == [0.0, 0.0, 0.0, 1.0, 0.0]

    # 2. Check median imputation values
    # Median of [20.0, 30.0, 40.0] is 30.0
    assert list(imputed_df["age"]) == [20.0, 30.0, 30.0, 30.0, 40.0]
    # Median of [50000, 70000, 90000, 100000] is 80000.0
    expected_salary_median = np.median([50000.0, 70000.0, 90000.0, 100000.0])
    assert imputed_df["salary"].isna().sum() == 0
    assert imputed_df.loc[3, "salary"] == expected_salary_median

    # 3. Check categorical missing handling
    assert imputed_df.loc[1, "dept"] == "missing"

    # 4. Critical Isolation Check: original df was NOT modified
    assert df["age"].isna().sum() == 2
    assert df["salary"].isna().sum() == 1
    assert "age_isna" not in df.columns


def test_modeling_algorithms_succeed_on_imputed_data():
    """Verify Ridge regression, KMeans, and PCA run without NaN choke on imputed data."""
    np.random.seed(42)
    n_rows = 50
    raw_x = np.random.randn(n_rows, 3)
    # Inject NaNs
    raw_x[0:10, 0] = np.nan
    raw_x[5:15, 1] = np.nan

    df = pd.DataFrame(raw_x, columns=["feat_a", "feat_b", "feat_c"])
    df["target"] = np.random.randn(n_rows)

    # Impute
    imputed_df, indicators = create_imputed_modeling_data(df)

    # Feature matrix for modeling (all numeric columns except target)
    feature_cols = [c for c in imputed_df.columns if c != "target"]
    X = imputed_df[feature_cols].to_numpy()
    y = imputed_df["target"].to_numpy()

    assert not np.isnan(X).any(), "Feature matrix contains NaNs!"

    # 1. Ridge regression
    ridge = Ridge()
    ridge.fit(X, y )
    preds = ridge.predict(X)
    assert len(preds) == n_rows

    # 2. KMeans clustering
    kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(X)
    assert len(clusters) == n_rows

    # 3. PCA decomposition
    pca = PCA(n_components=2)
    components = pca.fit_transform(X)
    assert components.shape == (n_rows, 2)
