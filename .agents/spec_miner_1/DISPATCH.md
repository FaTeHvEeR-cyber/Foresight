# Dispatch for Spec Miner 1
Task: Mine precise functional and non-functional requirements, API schemas, mathematical definitions, latency budgets, and footprint rules.
Working directory: d:\Foresight\.agents\spec_miner_1
Read: d:\Foresight\.agents\ORIGINAL_REQUEST.md, AGENTS.md, GEMINI.md, d:\Foresight\.agents\skills\model-inference-integration\SKILL.md, and any specs in repository.


## 2026-09-19T18:23:22Z
You are a Spec Miner analyzing requirements and specifications for Phase 3A Analytics.
Your working directory is d:\Foresight\.agents\spec_miner_1.
You must read d:\Foresight\.agents\ORIGINAL_REQUEST.md, d:\Foresight\AGENTS.md, d:\Foresight\GEMINI.md, and d:\Foresight\.agents\skills\model-inference-integration\SKILL.md first.
Task:
1. Mine exact requirements for R1-R5:
   - Feature Pipeline & Loader: Supported datasets (Bike Sharing, Online Retail, Wholesale Customers, Airline Passengers, Rossmann Store Sales), calendar features, lag features, rolling windows, categorical encodings (out-of-fold smoothed mean encoding, leakage-safe), multi-frequency handling.
   - Forecasting Engine: Models (XGBoost max_depth<=7, Ridge, MLP), lazy loading, caching registry, latency budget (< 100ms), dynamic vs pre-trained handling.
   - Hypothesis Engine: Welch's t-test (`scipy.stats.ttest_ind(equal_var=False)`), reporting lift %, t-stat, p-value, significance verdict.
   - API Router & Chart Orchestrator: Endpoints (`/api/v1/forecast`, `/api/v1/hypotheses`), payload request/response schemas, chart picker rules/recommendation logic.
   - Governance: < 50MB model ceiling, `joblib.dump(..., compress=3)`, `ephemeral_processing()` / `io.BytesIO`, README.md continuous logging requirement.
2. Cross-reference with any existing specs, docs, or contracts in the repository (e.g. `spec/`, `docs/`).
3. Output your comprehensive specification report to `d:\Foresight\.agents\spec_miner_1\handoff.md` and send a message back to parent when complete.
