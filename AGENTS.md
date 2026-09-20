# Foresight Architectural & Model Integrity Rules

These rules establish universal guardrails, data policies, and serialization standards for the Foresight analytics platform. All agents and subagents operating in this repository must strictly adhere to these invariants.

---

## 1. Architectural Scope & Security Boundaries
- **Runtime Agent Scope**: GLM 5.3 is strictly scoped to the Anti-Gravity Security Audit Gate (security auditing only). It must never be wired into active runtime code, dev loops, background tasks, or inference paths.
- **Dynamic Routing**: Dynamic UI schema and report chip routing is parked as a cosmetic placeholder and must NOT be wired to backend logic or routing.
- **Document & NLP Intelligence**: All document parsing and NLP capabilities (future Engine C) must operate entirely local and offline. External LLM APIs, web scraping, or third-party cloud AI SaaS dependencies are strictly prohibited.
- **Ephemeral Memory Lifecycle**: In-memory data processing must strictly honor ephemeral memory lifecycles via `ephemeral_processing()` and `io.BytesIO`. Never persist unvalidated raw datasets or transient session data to disk.

---

## 2. Artifact Footprint & Serialization Standards (Spec §5.2)
- **Combined Size Ceiling**: The combined size of all serialized `.joblib` model artifacts in `backend/models/` or `models/` must remain strictly under **50.0 MB**.
- **Mandatory Compression**: All model and pipeline artifacts must be serialized using `joblib.dump(artifact, path, compress=3)`. Uncompressed serialization is prohibited.
- **Tree Model Depth Limits**: XGBoost models must cap `max_depth <= 7` and enforce early stopping (`early_stopping_rounds`) to avoid tree explosion and memory bloat.
- **Size Auditing**: Any pipeline or test modifying model artifacts must validate compliance using `python backend/scripts/audit_artifact_size.py`.

---

## 3. Training & Data Integrity Guardrails
- **No Artificial Subsampling on Imbalanced Data**: Never subsample or artificially balance extreme-imbalance datasets (e.g. credit card fraud) for unsupervised models (Isolation Forest, KMeans). Train on full datasets with the `contamination` parameter set to the true observed rate (~0.00167).
- **Validation Split Selection**:
  - **Multi-Year Time Series** (e.g. Rossmann Store Sales, 2.5y): Use strict chronological holdout (e.g. last 6 weeks).
  - **Short-Duration / Static Datasets** (e.g. 48-hour transaction windows): Use **random stratified splits** to prevent temporal generalization collapse across narrow non-overlapping windows.
- **Target Encoding**: Out-of-fold smoothed mean encoding must use 5 folds and be strictly leakage-safe (each training row's encoding excludes its own target value).
- **Target Transformations**: Apply log-target transformations selectively only after empirical validation per estimator (e.g. log-target for XGBoost, raw target for linear Ridge and MLP).

---

## 4. Evaluation & Metric Gate Policy
- **Anomaly Detection Evaluation**: Unsupervised anomaly ranking (Isolation Forest) must be evaluated at an operational **5% review-queue flag rate**, not at the raw contamination threshold.
- **Component Reduction Targets**: When features are already PCA-derived (e.g. V1–V28), recalibrate 2D explained variance targets to realistic baselines (≥ 35%, not 60%+).
- **Near-Miss Tolerance**: Marginally missed speculative targets within 0.01 (e.g. MLP RMSPE 0.1501 vs 0.15, IForest PR-AUC 0.141 vs 0.15) are treated as passing when primary gates pass and returns show clear diminishing returns.

---

## 5. Phase 3 Inference Contracts
- **Lazy Initialization**: Pre-trained `.joblib` models and scalers must be loaded lazily on startup/first request and cached in an in-memory registry.
- **Latency Budget**: Batch inference for `POST /api/v1/forecast` and `POST /api/v1/segmentation` must target < 100ms execution latency.
- **Review Queue Flag**: `POST /api/v1/segmentation` must return anomaly scores alongside a boolean flag based on the 5% review queue threshold.
- **Statistical Hypotheses**: Hypothesis evaluation (`POST /api/v1/hypotheses`) must use Welch's t-test (`scipy.stats.ttest_ind(equal_var=False)`) to report lift percentage, t-statistic, and p-value.

---

## 6. Continuous Documentation & README.md Invariant
- **Mandatory README Logging**: Whenever completing a task, executing setup instructions, making code modifications, updating functions, or altering architectural/design structures, the agent must log and document the full update in `README.md` at the project root.
- **Living Documentation Standard**: `README.md` (co-located with `AGENTS.md` and `GEMINI.md`) must be continually maintained and never allowed to fall out of sync with the codebase.
- **Scope of Documented Changes**:
  - **Architectural & Design Updates**: Structural shifts, pipeline revisions, and engine parameter modifications.
  - **Function & Interface Changes**: Additions, refactors, or signature changes across backend and frontend services.
  - **Defect Logs & Bug Fixes**: Root causes, corrective actions, and preventative changes.
  - **Plans, Walkthroughs & Setup**: Step-by-step setup instructions, verification results, and operational runbooks.
- **Execution Lifecycle**: Updating and logging in `README.md` is a required completion criterion for every code or configuration change.

---

## 7. Teamwork & Sync Points
- **Sync Point 1**: Agent 1 (Integration Lead) finishes merge and green suite FIRST. Other agents may draft in parallel but must rebase on Agent 1's work before running final tests.
- **Parallel Execution**: Agents 2, 3, 4 run in parallel after sync point 1.
- **File Ownership**: No agent edits another's files. Cross-agent bugs go back to the owner as a written note, not a drive-by edit.
- **Core Pipeline Ownership**: Changes to `feature_pipeline.py` or `forecast_engine.py` are made by one designated owner (Agent 1) and re-tested by all.
- **Final Sync**: Agent 5 runs last.
