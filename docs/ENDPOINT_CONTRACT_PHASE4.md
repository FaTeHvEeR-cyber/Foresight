# Foresight Phase 4 Frontend Integration Contract

**Document Version**: 1.0.0  
**Target Audience**: Phase 4 Frontend Developers & UI Engineers  
**Backend Endpoints**: `POST /api/v1/forecast`, `POST /api/v1/hypotheses`  
**Base URL**: `http://localhost:8000/api/v1`  
**Authentication**: Zero-Auth / Stateless  
**CORS Policy**: Configured for `http://localhost:3000` and `http://127.0.0.1:3000` with `allow_credentials=True`.

---

## 1. Architectural Overview & Invariants

1. **Stateless Ephemeral Ingestion**:
   - The backend stores no session state, files, or raw tables on disk or database. Every request must supply its own file upload payload.
   - All processing executes in-memory; references are dropped and garbage collected immediately after the response is returned.
2. **Streaming 50 MB Size Guardrail**:
   - Maximum allowed upload payload size is **50.0 MB** (`52,428,800` bytes). Files exceeding this limit are terminated mid-stream with `HTTP 413 Content Too Large`.
3. **Structured Visualization Recommendations**:
   - Every 200 OK response includes a `recommended_visualization` object generated either by Google Gemini 3.8 Flash (analyzing aggregate metadata only) or deterministic heuristic rules.
   - The frontend should dynamically render the appropriate chart component based on `recommended_visualization.chart`.

---

## 2. Endpoint: `POST /api/v1/forecast`

Fits a dynamic fast-fit dual-model tournament (Ridge baseline vs histogram XGBoost) in memory, performs chronological holdout evaluation, selects the optimal regressor, and computes a multi-step recursive forecast with 95% confidence bounds.

### 2.1. Request Specification
- **Content-Type**: `multipart/form-data`
- **HTTP Method**: `POST`
- **Path**: `/api/v1/forecast`

| Field Name | Type | Presence | Default | Description |
| :--- | :--- | :---: | :---: | :--- |
| `file` | `File` (binary) | **Required** | — | Raw tabular file. Permitted extensions: `.csv`, `.tsv`, `.txt`, `.xlsx`, `.xls`, `.parquet`. Max size: 50.0 MB. |
| `target` | `string` | Optional | `null` | Column name of the numerical target variable to forecast. If omitted, the backend auto-detects the target using priority hints (e.g. `sales`, `cnt`, `target`, `revenue`) or the primary numeric series. |
| `date_col` | `string` | Optional | `null` | Column name containing date/timestamp values. If omitted, the backend automatically infers the date column via regex pattern matching and data type inspection. |
| `horizon` | `integer` | Optional | Auto | Number of future periods to forecast. Range: `1` to `60`. If omitted, the backend infers a sensible horizon based on frequency (e.g. 14 days for daily, 12 months for monthly). |
| `use_llm` | `boolean` | Optional | `true` | When `true`, requests Gemini 3.8 Flash to recommend the visualization. When `false` or during timeouts/rate limits, uses deterministic heuristics. |

### 2.2. Success Response Schema (`200 OK`)

```typescript
export interface ForecastSuccessResponse {
  status: "ok";
  dataset: {
    date_column: string;        // e.g. "dteday"
    target: string;             // e.g. "cnt"
    frequency: string;          // e.g. "daily", "weekly", "monthly", "quarterly"
    date_format: string;        // e.g. "day-first", "month-first", "iso"
    n_periods: number;          // Total valid chronological observations
    start: string;              // ISO Date "YYYY-MM-DD"
    end: string;                // ISO Date "YYYY-MM-DD"
  };
  series: {
    dates: string[];            // ISO Date strings for recent history (tail up to 365 periods)
    actuals: number[];          // Historical observed values
  };
  holdout: {
    dates: string[];            // Dates for the chronological validation holdout window
    actuals: number[];          // True observed holdout values
    predictions: {
      ridge?: number[];         // Predictions from regularized Ridge baseline
      xgboost?: number[];       // Predictions from histogram XGBoost regressor
    };
  };
  forecast: {
    model: "ridge" | "xgboost"; // Winning model selected by validation metrics
    horizon: number;            // Number of predicted steps
    dates: string[];            // Future forecast dates (length == horizon)
    values: number[];           // Point prediction values
    lower: number[];            // Lower 95% confidence bound (clamped at 0 for non-negative series)
    upper: number[];            // Upper 95% confidence bound
    interval_note: string;      // "Approximate 95% band (±1.96 × holdout RMSE), constant width."
  };
  metrics: {
    [model_name: string]: {
      rmspe: number | null;     // Root Mean Square Percentage Error (null if actuals contain 0s)
      mae: number;              // Mean Absolute Error
      rmse: number;             // Root Mean Square Error
      r2: number | null;        // R-squared score on holdout set
      n: number;                // Number of holdout evaluation samples
      n_zero_actuals_excluded_from_rmspe: number;
    };
  };
  selected_model: "ridge" | "xgboost";
  skill_vs_seasonal_naive: number | null; // e.g. 0.6353 (beats seasonal naive by 63.5%)
  features: {
    lags: number[];             // Dynamic lags selected based on frequency (e.g. [1, 2, 7, 14, 21, 28])
    rolling_windows: number[];  // Moving statistics windows
    holdout_periods: number;    // Number of holdout periods
    n_features: number;         // Total engineered feature dimensions
    exogenous_columns_lagged_1: string[]; // Exogenous covariates shifted by lag-1
  };
  preprocessing: {
    dropped_columns: Array<{
      name: string;
      reason: string;           // e.g. "ID / row counter", "target component"
    }>;
    categorical_candidates: string[];
    data_quality: {
      cancellation_rows_dropped?: number;
      cancellation_invoices?: number;
      [key: string]: any;
    };
    notes: string[];
  };
  timing_ms: {
    features: number;           // Feature engineering runtime in ms
    validation_fit: number;     // Dual model training & evaluation in ms
    refit_and_forecast: number; // Recursive forecasting loop in ms
    compute_total: number;      // Total model compute time (targeted < 100ms, budgeted < 200ms)
    load_parse: number;         // File ingestion and parsing runtime in ms
    prepare_series: number;     // Series preparation runtime in ms
    budget: number;             // Configured compute budget (e.g. 200ms)
    within_budget: boolean;     // Whether compute_total <= budget
  };
  recommended_visualization: RecommendedVisualization;
}
```

### 2.3. Degraded / Non-Error Responses (`200 OK`)

When the uploaded table is valid tabular data but cannot generate a forecast, the endpoint returns an HTTP 200 with a degraded status rather than throwing an exception:

#### Scenario A: Non-Temporal Table Uploaded (`no_date_column`)
```json
{
  "status": "no_date_column",
  "message": "No date column detected. Pass `date_col` explicitly.",
  "recommended_visualization": {
    "chart": "kpi_card",
    "reason": "Not enough data for a forecast chart; show the message as a card.",
    "source": "heuristic",
    "allowed": ["line_chart", "bar_comparison", "scatter_cluster", "kpi_card"],
    "latency_ms": 0.1
  }
}
```
*Frontend Action*: Display an informational card explaining that no date/time series was detected, offering a selector to choose a date column manually or navigate to `/hypotheses`.

#### Scenario B: Insufficient Observations (`insufficient_data`)
```json
{
  "status": "insufficient_data",
  "message": "Series has only 12 rows; minimum required is 15.",
  "recommended_visualization": {
    "chart": "kpi_card",
    "reason": "Not enough data for a forecast chart; show the message as a card.",
    "source": "heuristic",
    "allowed": ["line_chart", "bar_comparison", "scatter_cluster", "kpi_card"],
    "latency_ms": 0.1
  }
}
```
*Frontend Action*: Render a warning card requesting the user upload a longer time series.

---

## 3. Endpoint: `POST /api/v1/hypotheses`

Computes rigorous statistical hypothesis tests evaluating target metric lift across categorical groups, applying Welch's unequal variance t-test for 2-group comparisons and One-Way ANOVA for 3+ groups, with Holm-Bonferroni multi-testing adjustment and non-parametric cross-checks.

### 3.1. Request Specification
- **Content-Type**: `multipart/form-data`
- **HTTP Method**: `POST`
- **Path**: `/api/v1/hypotheses`

| Field Name | Type | Presence | Default | Description |
| :--- | :--- | :---: | :---: | :--- |
| `file` | `File` (binary) | **Required** | — | Raw tabular file (.csv, .tsv, .xlsx, .parquet). Max 50 MB. |
| `target` | `string` | Optional | `null` | Numeric target metric to test (e.g. `Sales`, `Order_Value`). If omitted, auto-detected from numeric columns. |
| `group_cols` | `string` | Optional | `null` | Comma-separated categorical column names to group by (e.g. `"Promo,StateHoliday"`). If omitted, all categorical candidates are evaluated. |
| `use_llm` | `boolean` | Optional | `true` | Whether to consult Gemini 3.8 Flash for visualization recommendations. |

### 3.2. Success Response Schema (`200 OK`)

```typescript
export interface HypothesesSuccessResponse {
  status: "ok";
  target: string;               // Target column evaluated (e.g. "Sales")
  message: string | null;
  alpha: number;                // Significance threshold (default: 0.05)
  tests: Array<HypothesisTestResult>;
  skipped: Array<{
    column: string;
    reason: string;             // e.g. "fewer than 2 groups with at least 5 rows"
  }>;
  notes: string[];              // Methodological notes (e.g. Holm correction, skew warnings)
  timing_ms: {
    compute_total: number;      // Total execution time in ms
  };
  recommended_visualization: RecommendedVisualization;
}

export interface HypothesisTestResult {
  test: "welch_t" | "anova";
  statistic: number;            // Welch's t-statistic or ANOVA F-statistic
  p_value: number;              // Unadjusted raw p-value
  p_value_adjusted: number;     // Holm-Bonferroni step-down corrected p-value
  significant: boolean;         // true if p_value_adjusted < alpha (0.05)
  significant_unadjusted: boolean;
  df: number | [number, number];// Degrees of freedom (float for Welch's, [df1, df2] for ANOVA)
  grouping_column: string;      // Category evaluated (e.g. "Promo")
  target: string;               // Evaluated target metric
  n_groups: number;             // Number of unique groups evaluated
  group_stats: Array<{
    group: string;              // Group label (e.g. "0" vs "1", "Control" vs "Treatment")
    n: number;                  // Sample size for this group
    mean: number;               // Group mean
    std: number;                // Group standard deviation
  }>;
  target_skew: number;          // Fisher-Pearson skewness of target distribution
  skew_warning: boolean;        // true if |skew| > 2.0 (indicates high skewness)
  nonparametric_p: number;      // Mann-Whitney U (2 groups) or Kruskal-Wallis (3+ groups) p-value
  robust: boolean;              // true if parametric and non-parametric tests agree on significance
  
  // Specific to Welch's t-test (2 groups only):
  baseline_group?: string;      // Group 0 label
  comparison_group?: string;    // Group 1 label
  mean_difference?: number;     // comparison_mean - baseline_mean
  lift_pct?: number | null;     // Percentage lift: ((comparison_mean / baseline_mean) - 1) * 100
  effect_size: {
    name: "cohens_d" | "eta_squared";
    value: number | null;       // Standardized effect size magnitude
  };
}
```

---

## 4. Visualization Recommendation Contract

Every successful endpoint response includes a `recommended_visualization` block:

```typescript
export interface RecommendedVisualization {
  chart: "line_chart" | "bar_comparison" | "scatter_cluster" | "kpi_card";
  reason: string;               // Concise rationale for this chart choice
  source: "llm" | "heuristic";  // Origin of recommendation
  allowed: string[];            // ["line_chart", "bar_comparison", "scatter_cluster", "kpi_card"]
  model?: string;               // "gemini-2.5-flash" (present when source === "llm")
  fallback_reason?: string;     // e.g. "llm_disabled", "no_api_key", "llm_http_429", "llm_error_ReadTimeout"
  latency_ms: number;           // Orchestration latency in ms
}
```

### 4.1. Chart Component Mapping Guide for Frontend

| Recommended Enum | Target Component | Data Source in Response | Recommended Frontend Presentation |
| :--- | :--- | :--- | :--- |
| `line_chart` | Time Series & Forecast Explorer | `res.series` + `res.forecast` + `res.holdout` | Render historical actuals in solid blue, forecast values in dashed teal, and fill 95% confidence bounds (`lower` to `upper`) with translucent shading. Provide toggle for validation holdout predictions. |
| `bar_comparison` | Group Lift & Hypothesis Bar | `res.tests[i].group_stats` | Horizontal or vertical grouped bar chart comparing group means with error bars ($\pm \text{std}/\sqrt{n}$). Badge with lift % and statistical significance badge ($p < 0.05$). |
| `scatter_cluster` | 2D Cluster & Outlier Projection | (Engine B / Phase 3B) | 2D PCA projection scatter plot color-coded by cluster assignment. Red circular pulse markers for review queue anomalies. |
| `kpi_card` | Summary Headline Metric Card | `res.message` or headline KPI | Large headline metric card accompanied by status badge, explanatory description, and latency/timing badges. |

---

## 5. HTTP Error Code Reference

The backend implements standard RFC 7807 problem details with consistent JSON error bodies:
```json
{
  "detail": "Error message explaining the exact validation or execution failure."
}
```

| HTTP Status | Exception Type | Trigger Conditions | User-Facing Guidance |
| :---: | :--- | :--- | :--- |
| **`400`** | `Bad Request` | Uploaded file is 0 bytes or completely empty (`EmptyFileError`). | *"The uploaded file contains no data. Please select a valid tabular file."* |
| **`413`** | `Content Too Large` | Upload payload exceeds 50.0 MB (`52,428,800` bytes). | *"File exceeds the 50 MB upload limit. Please compress or subsample your dataset."* |
| **`415`** | `Unsupported Media Type` | 1. Non-tabular extension (e.g. `.exe`, `.pdf`, `.zip`).<br>2. MIME type mismatch.<br>3. Executable magic bytes detected (`MZ`, `ELF`, shell script `#!`, `\x89PNG`).<br>4. Binary null bytes found in CSV/TSV. | *"Invalid or unsupported file format. Please upload a standard CSV, TSV, XLSX, or Parquet file."* |
| **`422`** | `Unprocessable Entity` | 1. Corrupt spreadsheet or unparseable CSV.<br>2. Specified `target` or `date_col` not found in headers.<br>3. Target column is non-numeric.<br>4. Target has zero variance across all rows.<br>5. Formula injection attack detected that corrupted structure. | *"The file structure could not be processed. Verify your column headers and ensure the target metric contains numeric values."* |
| **`500`** | `Internal Server Error` | Unexpected backend runtime or algorithmic failure. | *"An unexpected error occurred during model computation. Our engineering team has been notified."* |

---

## 6. Frontend Integration Examples (TypeScript / React)

### 6.1. Executing a Forecast Request
```typescript
import { ForecastSuccessResponse } from "@/types/analytics";

export async function uploadAndForecast(
  file: File,
  target?: string,
  dateCol?: string,
  horizon?: number
): Promise<ForecastSuccessResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (target) formData.append("target", target);
  if (dateCol) formData.append("date_col", dateCol);
  if (horizon) formData.append("horizon", horizon.toString());
  formData.append("use_llm", "true");

  const response = await fetch("http://localhost:8000/api/v1/forecast", {
    method: "POST",
    body: formData,
    credentials: "include", // Required for CORS credentials
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Network error" }));
    throw new Error(errorData.detail || `Upload failed with status ${response.status}`);
  }

  return response.json();
}
```

### 6.2. Rendering Dynamic Visualizations
```tsx
import React from "react";
import { LineChartForecast } from "@/components/charts/LineChartForecast";
import { BarComparison } from "@/components/charts/BarComparison";
import { KpiCard } from "@/components/charts/KpiCard";

export function AnalyticsResultView({ result }: { result: any }) {
  const chartType = result.recommended_visualization?.chart || "kpi_card";

  switch (chartType) {
    case "line_chart":
      return <LineChartForecast data={result} />;
    case "bar_comparison":
      return <BarComparison tests={result.tests} />;
    case "kpi_card":
    default:
      return (
        <KpiCard
          title={result.dataset?.target || result.target || "Notice"}
          message={result.message || "Computation completed successfully."}
          latencyMs={result.timing_ms?.compute_total}
        />
      );
  }
}
```
