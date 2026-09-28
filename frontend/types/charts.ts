export type ChartType =
  | "line_chart"
  | "bar_comparison"
  | "scatter_cluster"
  | "kpi_card"
  | "forecast_band_chart"
  | "bar_line_combo"
  | "box_plot"
  | "heatmap_correlation"
  | "outlier_table"
  | "histogram_distribution";

export interface RankedVisualization {
  charts: ChartType[];
  chart: ChartType; // Keep the old single recommendation working
  reason: string;
  source: "llm" | "heuristic";
  allowed: ChartType[];
  model?: string;
  fallback_reason?: string;
  latency_ms: number;
}
