# Model Inference Integration Runbook (Phase 3A & 3B)

Local dump for Worker Remediation 1.
Original Source: `d:\Foresight\.agents\skills\model-inference-integration\SKILL.md`

## Summary:
Runbook for integrating serialized Engine A (forecasting, Welch's t-test) and Engine B (KMeans clustering, PCA 2D, Isolation Forest anomaly scoring) .joblib models into Phase 3 FastAPI inference endpoints with lazy loading, sub-100ms latency, and artifact footprint compliance (<50 MB).
