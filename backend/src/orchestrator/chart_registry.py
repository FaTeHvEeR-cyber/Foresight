"""Chart expansion registry for Phase 3."""

ALLOWED = (
    "line_chart", "bar_comparison", "scatter_cluster", "kpi_card",
    "forecast_band_chart", "bar_line_combo", "box_plot",
    "heatmap_correlation", "outlier_table", "histogram_distribution"
)

# Example ranked JSON structure per ENDPOINT_CONTRACT_PHASE4.md
EXAMPLE_RANKED_JSON = {
    "charts": ["line_chart", "kpi_card"],
    "reason": "Time series with forecast horizon."
}
