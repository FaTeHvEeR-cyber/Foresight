# Foresight

Foresight is an intelligent forecasting system consisting of multiple predictive engines (Engine A for primary forecasting, Engine B for anomaly detection and clustering) with robust data ingestion, validation, and sanitization pipelines.

## Project Structure

- `backend/`: FastAPI backend powering the core predictive engines, data parsers, and endpoints.
- `frontend/`: Web interface interacting with the backend APIs.
- `models/`: Serialized models and artifacts.

---

## Architectural Decisions & Model Tuning

### Engine A (Forecasting)
- **Problem**: We encountered inflated Root Mean Square Percentage Error (RMSPE) metrics primarily on low-demand rows (e.g., units < 50), which was identified as a metric sensitivity artifact rather than a true model fit issue.
- **Tuning Insights**: After evaluating Ridge Regression, MLP Regressors, and XGBoost on a strict chronological split (with lag/rolling features without temporal leakage), we determined optimal hyperparameters for the XGBoost Regressor to hit strict performance thresholds (RMSPE <= 15%, R² >= 0.85).
- **Optimized Hyperparameters**: 
  - `max_depth` = 3
  - `n_estimators` = 100
  - `learning_rate` = 0.05

### Engine B (Anomaly & Clustering)
- Supports robust feature engineering and uses Isolation Forest for anomaly detection and KMeans / PCA for clustering. Validation thresholds require Silhouette Score >= 0.45 and 2D PCA Explained Variance >= 80%.

---

## Changelog & Recent Fixes

### Data Ingestion & Security
- **Size Guard Updates**: Replaced the deprecated Starlette constant `HTTP_413_REQUEST_ENTITY_TOO_LARGE` with `HTTP_413_CONTENT_TOO_LARGE` across validators, middleware, and tests to guarantee forward compatibility with FastAPI and Starlette.
- **Pandas Data Profiling**: Modified `pd.to_datetime` in the raw data profiler to explicitly use `format="mixed"` to silence dateutil fallback warnings.

### Code Quality & Typing
- **Type Checking (MyPy/Pyright)**: 
  - Resolved absolute import mapping errors in `tabular_parser.py` (`backend.src.models` -> `src.models`).
  - Addressed ExtensionArray limitations by explicitly coercing subset masks and features to `numpy` arrays via `.to_numpy()` before feeding them to Scikit-Learn pipelines (`Ridge.fit`) and boolean bitwise operations (`~`, `.sum()`).
  - Switched from direct attribute access (e.g., `.n_clusters`, `.n_components`) to `.get_params()` on Scikit-Learn estimators for strict typing compliance.
- **Linting (Flake8)**: Pruned several unused variables and unnecessary dependencies/imports in the test suite (`test_train_engine_a.py`, `test_train_engine_b_anomaly.py`, `test_upload_endpoint.py`). Removed unnecessary typecasting overhead on columns during tabular parsing. 
- **Tests**: Suppressed internal third-party warnings (`starlette.testclient`) in `pytest.ini` to keep standard outputs clean. The codebase currently passes all 180 unit/integration tests with zero warnings.

*(This file will be continually updated with upcoming architectural changes and features.)*
