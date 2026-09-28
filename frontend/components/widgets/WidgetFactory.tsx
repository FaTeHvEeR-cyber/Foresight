import React from "react";
import { ChartType } from "@/types/charts";

// Stub components (Agents 2 and 3 will implement these in their respective files)
// For now we use simple div placeholders so typecheck and tests pass.
export const LineChart = ({ data }: { data?: any }) => <div data-testid="chart-line_chart">Line Chart</div>;
export const BarComparison = ({ data }: { data?: any }) => <div data-testid="chart-bar_comparison">Bar Comparison</div>;
export const ScatterCluster = ({ data }: { data?: any }) => <div data-testid="chart-scatter_cluster">Scatter Cluster</div>;
export const KpiCard = ({ data, title, message }: { data?: any, title?: string, message?: string }) => (
  <div data-testid="chart-kpi_card">KPI Card: {title} - {message}</div>
);
export const ForecastBandChart = ({ data }: { data?: any }) => <div data-testid="chart-forecast_band_chart">Forecast Band Chart</div>;
export const BarLineCombo = ({ data }: { data?: any }) => <div data-testid="chart-bar_line_combo">Bar Line Combo</div>;
export const BoxPlot = ({ data }: { data?: any }) => <div data-testid="chart-box_plot">Box Plot</div>;
export const HeatmapCorrelation = ({ data }: { data?: any }) => <div data-testid="chart-heatmap_correlation">Heatmap Correlation</div>;
export const OutlierTable = ({ data }: { data?: any }) => <div data-testid="chart-outlier_table">Outlier Table</div>;
export const HistogramDistribution = ({ data }: { data?: any }) => <div data-testid="chart-histogram_distribution">Histogram Distribution</div>;

interface WidgetFactoryProps {
  chartType: string;
  data?: any;
}

export function WidgetFactory({ chartType, data }: WidgetFactoryProps) {
  switch (chartType as ChartType) {
    case "line_chart":
      return <LineChart data={data} />;
    case "bar_comparison":
      return <BarComparison data={data} />;
    case "scatter_cluster":
      return <ScatterCluster data={data} />;
    case "forecast_band_chart":
      return <ForecastBandChart data={data} />;
    case "bar_line_combo":
      return <BarLineCombo data={data} />;
    case "box_plot":
      return <BoxPlot data={data} />;
    case "heatmap_correlation":
      return <HeatmapCorrelation data={data} />;
    case "outlier_table":
      return <OutlierTable data={data} />;
    case "histogram_distribution":
      return <HistogramDistribution data={data} />;
    case "kpi_card":
      return <KpiCard data={data} />;
    default:
      // Unknown token -> safe fallback to kpi_card
      return <KpiCard title="Notice" message={`Unsupported chart type: ${chartType}`} data={data} />;
  }
}
