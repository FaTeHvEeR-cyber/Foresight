import "@testing-library/jest-dom";
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

  describe("Token resolution (each of the 10 tokens)", () => {
    chartTokens.forEach((token) => {
      it(`resolves ${token} to correct component with data-testid="chart-${token}"`, () => {
        render(<WidgetFactory chartType={token} />);
        expect(screen.getByTestId(`chart-${token}`)).toBeInTheDocument();
      });
    });
  });

  describe("Unmapped / unknown tokens fallback", () => {
    it("unmapped token falls back to KpiCard", () => {
      render(<WidgetFactory chartType="some_unknown_token" />);
      const kpiCard = screen.getByTestId("chart-kpi_card");
      expect(kpiCard).toBeInTheDocument();
      expect(kpiCard).toHaveTextContent("Unsupported chart type: some_unknown_token");
    });

    it("arbitrary unmapped token falls back to KpiCard with message", () => {
      render(<WidgetFactory chartType="pie_chart_unsupported" />);
      const kpiCard = screen.getByTestId("chart-kpi_card");
      expect(kpiCard).toBeInTheDocument();
      expect(kpiCard).toHaveTextContent("Unsupported chart type: pie_chart_unsupported");
    });
  });

  describe("Rendering with valid sample data without throwing", () => {
    chartTokens.forEach((token) => {
      it(`renders ${token} with valid sample data without throwing`, () => {
        const sampleData = {
          dates: ["2023-01-01"],
          actuals: [10],
          forecasts: [12],
          points: [{ x: 1, y: 2, clusterId: 0 }],
          value: 100,
          title: "Sample",
        };
        expect(() => {
          render(<WidgetFactory chartType={token} data={sampleData} />);
        }).not.toThrow();
        expect(screen.getByTestId(`chart-${token}`)).toBeInTheDocument();
      });
    });
  });

  describe("Rendering empty state with empty or undefined data", () => {
    it("renders with undefined data without throwing", () => {
      chartTokens.forEach((token) => {
        expect(() => {
          render(<WidgetFactory chartType={token} data={undefined} />);
        }).not.toThrow();
        expect(screen.getByTestId(`chart-${token}`)).toBeInTheDocument();
      });
    });

    it("renders with empty object data without throwing", () => {
      chartTokens.forEach((token) => {
        expect(() => {
          render(<WidgetFactory chartType={token} data={{}} />);
        }).not.toThrow();
        expect(screen.getByTestId(`chart-${token}`)).toBeInTheDocument();
      });
    });

    it("renders unmapped token with empty data without throwing", () => {
      expect(() => {
        render(<WidgetFactory chartType="unmapped_token" data={undefined} />);
      }).not.toThrow();
      expect(screen.getByTestId("chart-kpi_card")).toBeInTheDocument();
    });
  });
});
