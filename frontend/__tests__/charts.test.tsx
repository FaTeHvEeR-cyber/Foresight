import "@testing-library/jest-dom";
import '@testing-library/jest-dom';
import React from "react";
import { render, screen } from "@testing-library/react";
import { LineChart } from "../components/charts/LineChart";
import { ForecastBandChart } from "../components/charts/ForecastBandChart";
import { BarComparison } from "../components/charts/BarComparison";
import { BarLineCombo } from "../components/charts/BarLineCombo";
import { HistogramDistribution } from "../components/charts/HistogramDistribution";

// Mock recharts to avoid rendering SVGs in jsdom which often causes issues
jest.mock('recharts', () => {
  const Original = jest.requireActual('recharts');
  return {
    ...Original,
    ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
    LineChart: ({ children }: any) => <div data-testid="recharts-line-chart">{children}</div>,
    BarChart: ({ children }: any) => <div data-testid="recharts-bar-chart">{children}</div>,
    ComposedChart: ({ children }: any) => <div data-testid="recharts-composed-chart">{children}</div>,
  };
});

describe("Chart Components", () => {
  describe("LineChart", () => {
    it("renders gracefully with empty data", () => {
      render(<LineChart data={undefined} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders correctly with data", () => {
      const data = {
        dates: ["2023-01-01", "2023-01-02"],
        actuals: [10, 20],
        forecasts: [12, 22],
        metrics: { rmspe: 0, mae: 0, rmse: 0, r2: 0 },
        modelUsed: "ridge" as const
      };
      render(<LineChart data={data} />);
      expect(screen.getByTestId("chart-line_chart")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-line-chart")).toBeInTheDocument();
    });
  });

  describe("ForecastBandChart", () => {
    it("renders gracefully with empty data", () => {
      render(<ForecastBandChart data={undefined} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders correctly with data", () => {
      const data = {
        dates: ["2023-01-01"],
        actuals: [10],
        forecasts: [12],
        lower: [8],
        upper: [15],
        metrics: { rmspe: 0, mae: 0, rmse: 0, r2: 0 },
        modelUsed: "ridge" as const
      };
      render(<ForecastBandChart data={data} />);
      expect(screen.getByTestId("chart-forecast_band_chart")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-composed-chart")).toBeInTheDocument();
    });
  });

  describe("BarComparison", () => {
    it("renders gracefully with empty data", () => {
      render(<BarComparison data={undefined} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders correctly with Agent 1's hypothesis format", () => {
      const data = {
        testType: "welch_t_test",
        pValue: 0.04,
        isSignificant: true,
        alpha: 0.05,
        groups: ["A", "B"],
        tests: [{
          group_stats: [
            { group: "A", mean: 10, std: 2, n: 100 },
            { group: "B", mean: 12, std: 2, n: 100 }
          ]
        }]
      };
      render(<BarComparison data={data} />);
      expect(screen.getByTestId("chart-bar_comparison")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-bar-chart")).toBeInTheDocument();
    });
  });

  describe("BarLineCombo", () => {
    it("renders gracefully with empty data", () => {
      render(<BarLineCombo data={undefined} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders correctly with data array", () => {
      const data = [{ name: "A", barValue: 10, lineValue: 12 }];
      render(<BarLineCombo data={data} />);
      expect(screen.getByTestId("chart-bar_line_combo")).toBeInTheDocument();
    });
  });

  describe("HistogramDistribution", () => {
    it("renders gracefully with empty data", () => {
      render(<HistogramDistribution data={undefined} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders correctly with bins and frequencies", () => {
      const data = { bins: [0, 10, 20], frequencies: [5, 15, 2] };
      render(<HistogramDistribution data={data} />);
      expect(screen.getByTestId("chart-histogram_distribution")).toBeInTheDocument();
    });
  });
});
