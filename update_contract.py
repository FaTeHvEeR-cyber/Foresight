import re
with open('docs/ENDPOINT_CONTRACT_PHASE4.md', 'r') as f:
    content = f.read()

new_block = '''`	ypescript
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

export interface RecommendedVisualization {
  charts: ChartType[];
  chart: ChartType;
  reason: string;
  source: "llm" | "heuristic";
  allowed: ChartType[];
  model?: string;
  fallback_reason?: string;
  latency_ms: number;
}
`'''

content = re.sub(r'`	ypescript\nexport interface RecommendedVisualization {.*?}\n`', new_block, content, flags=re.DOTALL)

table_content = '''| Recommended Enum | Target Component | Data Source in Response | Recommended Frontend Presentation |
| :--- | :--- | :--- | :--- |
| line_chart | Time Series & Forecast | es.series + es.forecast | Line chart of historical actuals and forecast. |
| ar_comparison | Group Lift & Hypothesis | es.tests[i].group_stats | Grouped bar chart comparing group means. |
| scatter_cluster | 2D Cluster & Outlier | (Engine B) | 2D PCA projection scatter plot by cluster. |
| kpi_card | Summary Headline Metric | es.message or KPI | Large headline metric card with text. |
| orecast_band_chart | Time Series with Bounds | es.series + bounds | Line chart with translucent confidence bands. |
| ar_line_combo | Dual-Axis Combo | Aggregations | Bars for volume, line for rates on dual Y-axes. |
| ox_plot | Distribution Quartiles | Grouped statistics | Box plot for median, quartiles, and outliers. |
| heatmap_correlation | Matrix Heatmap | Correlation matrices | 2D grid with color intensity. |
| outlier_table | Tabular Data Grid | es.anomalies | Sortable HTML table of anomaly records. |
| histogram_distribution | Frequency Dist | es.bins | Binned column chart showing frequency. |'''

content = re.sub(r'\| Recommended Enum.*?\| latency/timing badges\. \|', table_content, content, flags=re.DOTALL)

with open('docs/ENDPOINT_CONTRACT_PHASE4.md', 'w') as f:
    f.write(content)
