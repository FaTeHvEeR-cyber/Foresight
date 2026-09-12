/**
 * Phase 1 — REST Data Contracts
 * These interfaces define the shape of responses from the FastAPI backend.
 */

export type DetectedFileKind = "tabular" | "document" | "mixed";

export type DetectedFormat =
  | "csv"
  | "tsv"
  | "xlsx"
  | "xls"
  | "parquet"
  | "pdf"
  | "docx"
  | "txt"
  | "md";

export interface ColumnDescriptor {
  name: string;
  inferredType: "numeric" | "categorical" | "datetime" | "text" | "boolean";
  nullCount: number;
  nullPercentage?: number;
}

export interface ColumnNullProfile {
  nullCount: number;
  nullPercentage: number;
  totalRows: number;
}

export interface UploadResponse {
  fileId: string;
  fileName: string;
  fileSizeBytes: number;
  detectedKind: DetectedFileKind;
  detectedFormat: DetectedFormat;
  rowCount?: number;
  columnCount?: number;
  columns?: ColumnDescriptor[];
  rawNullProfile?: Record<string, ColumnNullProfile>;
  memoryUsageBytes: number;
}

export interface ForecastResponse {
  dates: string[];
  actuals: number[];
  forecasts: number[];
  metrics: {
    rmspe: number;
    mae: number;
    rmse: number;
    r2: number;
  };
  modelUsed: "ridge" | "xgboost" | "mlp";
}

export interface HypothesisResponse {
  testType: "welch_t_test" | "anova";
  pValue: number;
  isSignificant: boolean;
  alpha: number;
  groups: string[];
}

export interface SegmentationResponse {
  points: Array<{ x: number; y: number; clusterId: number }>;
  clusterCount: number;
  outlierMask: boolean[];
  outlierScoreMethod: "isolation_forest";
}

/**
 * Engine C — document summarization (local/offline NLP).
 */
export interface DocumentSummaryResponse {
  summary: string;
  keyTakeaways: string[];
  detectedDocType: "contract" | "report" | "policy" | "general";
  extractedTables?: Array<{ caption?: string; rows: string[][] }>;
}

/** Union of all four possible engine outputs tagged with "kind". */
export type AnalysisResult =
  | { kind: "forecast"; data: ForecastResponse }
  | { kind: "hypothesis"; data: HypothesisResponse }
  | { kind: "segmentation"; data: SegmentationResponse }
  | { kind: "document_summary"; data: DocumentSummaryResponse };
