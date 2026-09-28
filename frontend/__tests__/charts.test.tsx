import "@testing-library/jest-dom";
import React from "react";
import { render, screen } from "@testing-library/react";

// Agent 2 chart components
import { LineChart } from "../components/charts/LineChart";
import { ForecastBandChart } from "../components/charts/ForecastBandChart";
import { BarComparison } from "../components/charts/BarComparison";
import { BarLineCombo } from "../components/charts/BarLineCombo";
import { HistogramDistribution } from "../components/charts/HistogramDistribution";

// Agent 3 chart components
import { KpiCard } from "../components/charts/KpiCard";
import { OutlierTable } from "../components/charts/OutlierTable";
import { HeatmapCorrelation } from "../components/charts/HeatmapCorrelation";
import { ScatterCluster } from "../components/charts/ScatterCluster";
import { BoxPlot } from "../components/charts/BoxPlot";

// Mock recharts containers to avoid jsdom layout/SVG measurement issues
jest.mock("recharts", () => {
  const Original = jest.requireActual("recharts");
  return {
    ...Original,
    ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
    LineChart: ({ children }: any) => <div data-testid="recharts-line-chart">{children}</div>,
    BarChart: ({ children }: any) => <div data-testid="recharts-bar-chart">{children}</div>,
    ComposedChart: ({ children }: any) => <div data-testid="recharts-composed-chart">{children}</div>,
    ScatterChart: ({ children }: any) => <div data-testid="recharts-scatter-chart">{children}</div>,
  };
});

describe("Chart Components - Comprehensive Suite (10 Components)", () => {
  // 1. LineChart
  describe("LineChart", () => {
    it("renders with valid sample data without throwing", () => {
      const data = {
        dates: ["2023-01-01", "2023-01-02"],
        actuals: [100, 120],
        forecasts: [105, 125],
        metrics: { rmspe: 0.05, mae: 5, rmse: 6, r2: 0.95 },
        modelUsed: "ridge" as const,
      };
      render(<LineChart data={data} />);
      expect(screen.getByTestId("chart-line_chart")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-line-chart")).toBeInTheDocument();
    });

    it("renders the empty state with undefined data", () => {
      render(<LineChart data={undefined} />);
      expect(screen.getByTestId("chart-line_chart")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders the empty state with empty dates array", () => {
      render(<LineChart data={{ dates: [] } as any} />);
      expect(screen.getByTestId("chart-line_chart")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });
  });

  // 2. ForecastBandChart
  describe("ForecastBandChart", () => {
    it("renders with valid sample data without throwing", () => {
      const data = {
        dates: ["2023-01-01", "2023-01-02"],
        actuals: [100, 120],
        forecasts: [105, 125],
        lower: [90, 110],
        upper: [120, 140],
        metrics: { rmspe: 0.05, mae: 5, rmse: 6, r2: 0.95 },
        modelUsed: "ridge" as const,
      };
      render(<ForecastBandChart data={data} />);
      expect(screen.getByTestId("chart-forecast_band_chart")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-composed-chart")).toBeInTheDocument();
    });

    it("renders the empty state with undefined data", () => {
      render(<ForecastBandChart data={undefined} />);
      expect(screen.getByTestId("chart-forecast_band_chart")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders the empty state with empty dates array", () => {
      render(<ForecastBandChart data={{ dates: [] } as any} />);
      expect(screen.getByTestId("chart-forecast_band_chart")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });
  });

  // 3. BarComparison
  describe("BarComparison", () => {
    it("renders with valid sample data without throwing", () => {
      const data = {
        testType: "welch_t_test",
        pValue: 0.04,
        isSignificant: true,
        alpha: 0.05,
        groups: ["Control", "Treatment"],
        tests: [
          {
            group_stats: [
              { group: "Control", mean: 10, std: 2, n: 100 },
              { group: "Treatment", mean: 12, std: 2, n: 100 },
            ],
          },
        ],
      };
      render(<BarComparison data={data} />);
      expect(screen.getByTestId("chart-bar_comparison")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-bar-chart")).toBeInTheDocument();
    });

    it("renders the empty state with undefined data", () => {
      render(<BarComparison data={undefined} />);
      expect(screen.getByTestId("chart-bar_comparison")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders the empty state with empty array data", () => {
      render(<BarComparison data={[]} />);
      expect(screen.getByTestId("chart-bar_comparison")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });
  });

  // 4. BarLineCombo
  describe("BarLineCombo", () => {
    it("renders with valid sample data without throwing", () => {
      const data = [
        { name: "Jan", barValue: 10, lineValue: 12 },
        { name: "Feb", barValue: 15, lineValue: 18 },
      ];
      render(<BarLineCombo data={data} />);
      expect(screen.getByTestId("chart-bar_line_combo")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-composed-chart")).toBeInTheDocument();
    });

    it("renders the empty state with undefined data", () => {
      render(<BarLineCombo data={undefined} />);
      expect(screen.getByTestId("chart-bar_line_combo")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders the empty state with empty array data", () => {
      render(<BarLineCombo data={[]} />);
      expect(screen.getByTestId("chart-bar_line_combo")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });
  });

  // 5. HistogramDistribution
  describe("HistogramDistribution", () => {
    it("renders with valid sample data without throwing", () => {
      const data = { bins: [0, 10, 20, 30], frequencies: [5, 15, 25, 8] };
      render(<HistogramDistribution data={data} />);
      expect(screen.getByTestId("chart-histogram_distribution")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-bar-chart")).toBeInTheDocument();
    });

    it("renders the empty state with undefined data", () => {
      render(<HistogramDistribution data={undefined} />);
      expect(screen.getByTestId("chart-histogram_distribution")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders the empty state with empty array data", () => {
      render(<HistogramDistribution data={[]} />);
      expect(screen.getByTestId("chart-histogram_distribution")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });
  });

  // 6. KpiCard
  describe("KpiCard", () => {
    it("renders with valid sample data without throwing", () => {
      render(<KpiCard title="Active Users" value={1250} trend={{ value: 12, isPositive: true }} description="vs last week" />);
      expect(screen.getByTestId("chart-kpi_card")).toBeInTheDocument();
      expect(screen.getByText("Active Users")).toBeInTheDocument();
      expect(screen.getByText("1250")).toBeInTheDocument();
      expect(screen.getByText("+12%")).toBeInTheDocument();
      expect(screen.getByText("vs last week")).toBeInTheDocument();
    });

    it("renders the empty state with null value", () => {
      render(<KpiCard title="Test KPI" value={null as any} />);
      expect(screen.getByTestId("chart-kpi_card")).toBeInTheDocument();
      expect(screen.getByText("--")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders the empty state with undefined data", () => {
      render(<KpiCard data={undefined} value={undefined} />);
      expect(screen.getByTestId("chart-kpi_card")).toBeInTheDocument();
      expect(screen.getByText("--")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });
  });

  // 7. OutlierTable
  describe("OutlierTable", () => {
    it("renders with valid sample data without throwing", () => {
      const data = [
        { id: "row-1", amount: 5000, risk_score: 0.98 },
        { id: "row-2", amount: 4200, risk_score: 0.91 },
      ];
      render(<OutlierTable data={data} />);
      expect(screen.getByTestId("chart-outlier_table")).toBeInTheDocument();
      expect(screen.getByText("row-1")).toBeInTheDocument();
      expect(screen.getByText("5000")).toBeInTheDocument();
    });

    it("renders the empty state with empty array data", () => {
      render(<OutlierTable data={[]} />);
      expect(screen.getByTestId("chart-outlier_table")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders the empty state with undefined data", () => {
      render(<OutlierTable data={undefined} />);
      expect(screen.getByTestId("chart-outlier_table")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("asserts cap: limits outlier table to 100 rows by default", () => {
      const largeData = Array.from({ length: 150 }).map((_, i) => ({
        id: `outlier-${i}`,
        val: i * 10,
      }));
      const { container } = render(<OutlierTable data={largeData} />);
      expect(screen.getByTestId("chart-outlier_table")).toBeInTheDocument();
      // Assert only 100 rows rendered in tbody
      const rows = container.querySelectorAll("tbody tr");
      expect(rows).toHaveLength(100);
      // Assert cap notice text
      expect(screen.getByText(/Showing first 100 out of 150 outliers/i)).toBeInTheDocument();
    });
  });

  // 8. HeatmapCorrelation
  describe("HeatmapCorrelation", () => {
    it("renders with valid sample data without throwing", () => {
      const vars = ["varA", "varB"];
      const data = [
        { x: "varA", y: "varA", value: 1.0 },
        { x: "varA", y: "varB", value: 0.65 },
        { x: "varB", y: "varA", value: 0.65 },
        { x: "varB", y: "varB", value: 1.0 },
      ];
      render(<HeatmapCorrelation data={data} variables={vars} />);
      expect(screen.getByTestId("chart-heatmap_correlation")).toBeInTheDocument();
      expect(screen.getByTitle("varA vs varB: 0.65")).toBeInTheDocument();
    });

    it("renders the empty state with empty array data", () => {
      render(<HeatmapCorrelation data={[]} />);
      expect(screen.getByTestId("chart-heatmap_correlation")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders the empty state with undefined data", () => {
      render(<HeatmapCorrelation data={undefined} />);
      expect(screen.getByTestId("chart-heatmap_correlation")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("asserts cap: limits heatmap to 50x50 variables by default", () => {
      const vars = Array.from({ length: 60 }).map((_, i) => `v${i}`);
      const data = [{ x: vars[0], y: vars[1], value: 0.5 }];
      render(<HeatmapCorrelation data={data} variables={vars} />);
      expect(screen.getByTestId("chart-heatmap_correlation")).toBeInTheDocument();
      // Assert cap notice text
      expect(screen.getByText(/Showing correlation matrix capped at 50x50 variables/i)).toBeInTheDocument();
    });
  });

  // 9. ScatterCluster
  describe("ScatterCluster", () => {
    it("renders with valid sample data without throwing", () => {
      const data = {
        points: [
          { x: 1, y: 2, clusterId: 0 },
          { x: 3, y: 4, clusterId: 1 },
        ],
        clusterCount: 2,
        outlierMask: [false, true],
        outlierScoreMethod: "isolation_forest" as const,
      };
      render(<ScatterCluster data={data} />);
      expect(screen.getByTestId("chart-scatter_cluster")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-scatter-chart")).toBeInTheDocument();
    });

    it("renders the empty state with undefined data", () => {
      render(<ScatterCluster data={undefined} />);
      expect(screen.getByTestId("chart-scatter_cluster")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders the empty state with empty points array", () => {
      render(<ScatterCluster data={{ points: [] } as any} />);
      expect(screen.getByTestId("chart-scatter_cluster")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });
  });

  // 10. BoxPlot
  describe("BoxPlot", () => {
    it("renders with valid sample data without throwing", () => {
      const data = [
        { category: "Cat A", min: 10, q1: 20, median: 30, q3: 40, max: 50, outliers: [55] },
        { category: "Cat B", min: 15, q1: 25, median: 35, q3: 45, max: 60 },
      ];
      render(<BoxPlot data={data} />);
      expect(screen.getByTestId("chart-box_plot")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-bar-chart")).toBeInTheDocument();
    });

    it("renders the empty state with undefined data", () => {
      render(<BoxPlot data={undefined} />);
      expect(screen.getByTestId("chart-box_plot")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders the empty state with empty array data", () => {
      render(<BoxPlot data={[]} />);
      expect(screen.getByTestId("chart-box_plot")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });
  });
});
