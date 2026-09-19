---
name: model-inference-integration
description: >-
  Runbook for integrating serialized Engine A (forecasting, Welch's t-test) and
  Engine B (KMeans clustering, PCA 2D, Isolation Forest anomaly scoring) .joblib
  models into Phase 3 FastAPI inference endpoints with lazy loading, sub-100ms latency,
  and artifact footprint compliance.
---

# Model Inference Integration Runbook (Phase 3A & 3B)

This skill guides the implementation and verification of FastAPI inference endpoints using the serialized Phase 2.5 model artifacts.

## Serialized Artifact Inventory

Location: `backend/models/` (or repository root `models/`)

### Engine A (Forecasting & Hypotheses)
- `xgboost_primary.joblib` — Primary regressor (trained on log-transformed sales target)
- `ridge_baseline.joblib` — Linear baseline regressor (trained on raw sales target)
- `mlp_benchmark.joblib` — Neural network benchmark regressor (trained on raw sales target)
- `engine_a_scaler.joblib` — Feature scaler (`StandardScaler`)
- `engine_a_features.joblib` — Expected feature column schema & order

### Engine B (Clustering & Anomaly)
- `isolation_forest.joblib` — Anomaly scoring estimator (trained on full dataset, contamination=0.00167)
- `kmeans_k4.joblib` — K-Means behavioral clustering (k=4)
- `pca_2d.joblib` — 2D PCA projection for visualization
- `scaler.joblib` — RobustScaler/StandardScaler for features

---

## Integration Procedure

### 1. Lazy Model Loader Service (`backend/app/services/model_loader.py`)
Implement a singleton or caching registry that lazily deserializes models on startup or first access:

```python
import joblib
from pathlib import Path
from typing import Dict, Any

class ModelRegistry:
    _models: Dict[str, Any] = {}

    @classmethod
    def get_model(cls, artifact_name: str) -> Any:
        if artifact_name not in cls._models:
            model_path = Path(__file__).resolve().parent.parent.parent / "models" / artifact_name
            cls._models[artifact_name] = joblib.load(model_path)
        return cls._models[artifact_name]
```

### 2. Phase 3A: Forecasting & Hypothesis Endpoints
- **`POST /api/v1/forecast`**:
  - Accepts tabular input data or `file_id` referencing preprocessed session data.
  - Applies `engine_a_scaler.joblib` to ordered feature set.
  - Generates predictions using `xgboost_primary.joblib`. Remember to apply `np.expm1()` if predictions were trained in log space!
  - Optionally returns benchmark predictions from Ridge and MLP if requested in query parameters.
- **`POST /api/v1/hypotheses`**:
  - Implements statistical tests (e.g. Welch's t-test comparing promo vs. non-promo periods via `scipy.stats.ttest_ind(equal_var=False)`).
  - Returns lift percentage, t-statistic, p-value, and human-readable significance verdict.

### 3. Phase 3B: Segmentation & Anomaly Endpoints
- **`POST /api/v1/segmentation`**:
  - Scales input features via `scaler.joblib`.
  - Computes cluster assignments using `kmeans_k4.joblib`.
  - Computes 2D visualization coordinates via `pca_2d.joblib.transform()`.
  - Computes anomaly scores via `isolation_forest.joblib.score_samples()` or `decision_function()`.
  - Sets `is_anomaly_flag` using the calibrated **5% review queue threshold** (top 5% most anomalous scores), NOT the raw contamination threshold.

### 4. Verification & Validation Steps
1. **Latency Verification**: Run benchmark scripts against endpoints to ensure batch inference executes under 100ms.
2. **Artifact Footprint Check**:
   ```bash
   python backend/scripts/audit_artifact_size.py --ceiling-mb 50.0
   ```
3. **Regression Tests**:
   Run existing test suite to ensure zero regressions:
   ```bash
   pytest backend/tests/
   ```
