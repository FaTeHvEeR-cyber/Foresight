# Model Inference Integration Runbook (Phase 3A & 3B) - Local Challenger Copy

Source: d:\Foresight\.agents\skills\model-inference-integration\SKILL.md

Runbook for integrating serialized Engine A (forecasting, Welch's t-test) and Engine B (KMeans clustering, PCA 2D, Isolation Forest anomaly scoring) .joblib models into Phase 3 FastAPI inference endpoints with lazy loading, sub-100ms latency, and artifact footprint compliance.

Key endpoints & contracts:
- `POST /api/v1/forecast`:
  - Accepts tabular input or time series data / file_id
  - Applies engine_a_scaler.joblib to ordered feature set
  - Generates predictions using xgboost_primary.joblib (with np.expm1 if log-transformed)
  - Evaluates short horizons, zero/high values, non-negative bounds
- `POST /api/v1/hypotheses`:
  - Implements statistical tests (Welch's t-test via scipy.stats.ttest_ind(equal_var=False))
  - Reports lift percentage, t-statistic, p-value, and significance verdict
  - Evaluates unequal sample sizes and variances, edge cases (zero variance, small n)
- Latency budget: < 100ms
- Artifact footprint: < 50.0 MB ceiling
