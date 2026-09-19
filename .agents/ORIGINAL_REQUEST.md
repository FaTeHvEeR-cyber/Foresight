# Original User Request

## 2026-09-19T18:22:08Z

Implement and integrate the full Phase 3A analytics suite into Foresight's backend, delivering automated feature engineering, forecasting engines, hypothesis testing, chart picking, and API endpoints while preserving zero regressions across existing security and ingestion suites.

Working directory: d:\Foresight
Integrity mode: demo

## Requirements

### R1. Feature Pipeline and Data Loader
Implement an automated feature engineering pipeline and loader (`backend/src/analytics/feature_pipeline.py`, `backend/src/analytics/loader.py`) capable of handling diverse tabular and time-series datasets (such as Bike Sharing, Online Retail, Wholesale Customers, Airline Passengers, and Rossmann Store Sales) with proper temporal lag, rolling window, calendar, and categorical encodings.

### R2. Forecasting and Hypothesis Engines
Develop the core analytics engines (`backend/src/analytics/forecast_engine.py`, `backend/src/analytics/hypothesis_engine.py`):
- Forecasting engine supporting pre-trained and dynamically trained regression models (e.g., XGBoost, Ridge, MLP baselines) with lazy loading and < 100ms batch inference latency.
- Hypothesis testing engine implementing Welch's t-test (`scipy.stats.ttest_ind(equal_var=False)`) reporting lift percentage, t-statistic, p-value, and human-readable significance verdict.

### R3. Analytics Router and Chart Orchestrator
Build the API layer and visualization orchestrator (`backend/src/api/analytics_router.py`, `backend/src/orchestrator/chart_picker.py`, `backend/config/settings.py`):
- Expose RESTful endpoints (e.g., `/api/v1/forecast`, `/api/v1/hypotheses`) integrated with the existing FastAPI application.
- Implement an automated chart picker that inspects input schemas and statistical results to recommend appropriate visualizations.

### R4. Test Coverage and Regression Safety
Add comprehensive Phase 3A test coverage (`backend/tests/test_phase3a.py`, updating `backend/tests/conftest.py` as required) validating pipeline transformations, forecast latency, hypothesis computations, and endpoint behavior against real and synthetic datasets while ensuring zero regressions across existing Phase 2 security and ingestion tests (180+ tests passing).

### R5. Governance, Footprint, and Documentation
Maintain strict adherence to Foresight architectural invariants:
- Keep all serialized model artifacts strictly under the 50.0 MB combined ceiling with `joblib.dump(..., compress=3)`.
- Strictly enforce ephemeral memory processing for transient session data.
- Update `README.md` at the project root with the architectural updates, endpoint documentation, and verification results.

## Acceptance Criteria

### Analytics & Forecasting
- [ ] Feature pipeline successfully transforms multi-frequency time-series and tabular benchmark datasets into aligned model-ready matrices.
- [ ] Forecasting engine delivers batch predictions under 100ms latency budget.
- [ ] Hypothesis engine accurately evaluates statistical significance via Welch's t-test with lift, p-value, and test statistics.

### API & Orchestration
- [ ] Analytics router endpoints (`/api/v1/forecast`, `/api/v1/hypotheses`) respond with correct payload contracts and status codes.
- [ ] Chart picker accurately suggests visualization types based on data characteristics and hypothesis results.

### Test & Regression Quality
- [ ] Phase 3A test suite (`pytest backend/tests/test_phase3a.py`) passes all unit and integration tests.
- [ ] Existing test suite (`pytest backend/tests/`) passes with 0 regressions.
- [ ] Serialized artifact footprint remains under 50.0 MB verified by `python backend/scripts/audit_artifact_size.py`.
- [ ] `README.md` is updated with Phase 3A design, endpoint schemas, and test run results.
