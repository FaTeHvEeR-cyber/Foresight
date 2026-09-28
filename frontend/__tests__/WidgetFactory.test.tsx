import React from "react";
import { render, screen } from "@testing-library/react";
import { WidgetFactory } from "../components/widgets/WidgetFactory";
import { ChartType } from "../types/charts";

describe("WidgetFactory dispatcher", () => {
  const chartTokens: ChartType[] = [
    "line_chart",
    "bar_comparison",
    "scatter_cluster",
    "kpi_card",
    "forecast_band_chart",
    "bar_line_combo",
    "box_plot",
    "heatmap_correlation",
    "outlier_table",
    "histogram_distribution",
  ];

  chartTokens.forEach((token) => {
    it(`renders component for known token: ${token}`, () => {
      render(<WidgetFactory chartType={token} />);
      expect(screen.getByTestId(`chart-${token}`)).toBeInTheDocument();
    });
  });

  it("safely falls back to KPI card for unknown token", () => {
    render(<WidgetFactory chartType="some_unknown_token" />);
    // Should render the kpi_card fallback
    const kpiCard = screen.getByTestId("chart-kpi_card");
    expect(kpiCard).toBeInTheDocument();
    expect(kpiCard).toHaveTextContent("Unsupported chart type: some_unknown_token");
  });
});
