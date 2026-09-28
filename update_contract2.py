with open('docs/ENDPOINT_CONTRACT_PHASE4.md', 'r') as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if line.startswith('export interface RecommendedVisualization {'):
        skip = True
        new_lines.append('''export type ChartType =
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
''')
        continue
    if skip and line.strip() == '}':
        skip = False
        new_lines.append('}\n')
        continue
    if not skip:
        new_lines.append(line)

with open('docs/ENDPOINT_CONTRACT_PHASE4.md', 'w') as f:
    f.writelines(new_lines)
