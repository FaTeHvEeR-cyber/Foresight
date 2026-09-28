with open('docs/ENDPOINT_CONTRACT_PHASE4.md', 'r') as f:
    text = f.read()

import re

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

text = re.sub(r'\| Recommended Enum \| Target Component.*\| latency/timing badges\. \|', table_content, text, flags=re.DOTALL)
text = text.replace('4-choice', '10-choice')
text = text.replace('["line_chart", "bar_comparison", "scatter_cluster", "kpi_card"]', 'ChartType[]')
text = text.replace('line_chart | ar_comparison | scatter_cluster | kpi_card', 'ChartType')

with open('docs/ENDPOINT_CONTRACT_PHASE4.md', 'w') as f:
    f.write(text)
