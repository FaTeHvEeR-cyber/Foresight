import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import { KpiCard } from "../components/charts/KpiCard";
import { OutlierTable } from "../components/charts/OutlierTable";
import { HeatmapCorrelation } from "../components/charts/HeatmapCorrelation";
import { ScatterCluster } from "../components/charts/ScatterCluster";
import { BoxPlot } from "../components/charts/BoxPlot";

// Mock recharts
jest.mock("recharts", () => {
  const Original = jest.requireActual("recharts");
  return {
    ...Original,
    ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
    ScatterChart: ({ children }: any) => <div data-testid="recharts-scatter-chart">{children}</div>,
    BarChart: ({ children }: any) => <div data-testid="recharts-bar-chart">{children}</div>,
  };
});

describe("Agent 3 Chart Components", () => {
  describe("KpiCard", () => {
    it("renders gracefully with empty data", () => {
      render(<KpiCard title="Test KPI" value={null as any} />);
      expect(screen.getByText("--")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders gracefully with undefined data and value", () => {
      render(<KpiCard data={undefined} value={undefined} />);
      expect(screen.getByText("--")).toBeInTheDocument();
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders correctly with data", () => {
      render(<KpiCard title="Test KPI" value={100} trend={{ value: 5, isPositive: true }} />);
      expect(screen.getByText("100")).toBeInTheDocument();
      expect(screen.getByText("+5%")).toBeInTheDocument();
    });
  });

  describe("OutlierTable", () => {
    it("renders gracefully with empty data", () => {
      render(<OutlierTable data={[]} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders gracefully with undefined data", () => {
      render(<OutlierTable data={undefined} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders correctly with data", () => {
      const data = [{ id: 1, val: 42 }];
      render(<OutlierTable data={data} />);
      expect(screen.getByTestId("chart-outlier_table")).toBeInTheDocument();
      expect(screen.getByText("42")).toBeInTheDocument();
    });

    it("renders correctly with data and caps rows", () => {
      const data = Array.from({ length: 150 }).map((_, i) => ({ id: i, val: i }));
      const { container } = render(<OutlierTable data={data} maxRows={100} />);
      expect(screen.getByText(/Showing first 100/i)).toBeInTheDocument();
      expect(container.querySelectorAll("tbody tr")).toHaveLength(100);
    });

    it("caps outlier table to 100 rows by default without maxRows prop", () => {
      const data = Array.from({ length: 150 }).map((_, i) => ({ id: `row-${i}`, val: i }));
      const { container } = render(<OutlierTable data={data} />);
      expect(screen.getByText(/Showing first 100 out of 150 outliers/i)).toBeInTheDocument();
      expect(container.querySelectorAll("tbody tr")).toHaveLength(100);
    });
  });

  describe("HeatmapCorrelation", () => {
    it("renders gracefully with empty data", () => {
      render(<HeatmapCorrelation data={[]} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders gracefully with undefined data", () => {
      render(<HeatmapCorrelation data={undefined} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders gracefully with malformed data", () => {
      render(<HeatmapCorrelation data={[{}] as any} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders correctly with data and caps variables", () => {
      const vars = Array.from({ length: 60 }).map((_, i) => `var${i}`);
      const data = [{ x: vars[0], y: vars[1], value: 0.5 }];
      render(<HeatmapCorrelation data={data} variables={vars} maxVars={50} />);
      expect(screen.getByText(/Showing correlation matrix capped/i)).toBeInTheDocument();
    });

    it("caps heatmap to 50x50 variables by default without maxVars prop", () => {
      const vars = Array.from({ length: 60 }).map((_, i) => `var${i}`);
      const data = [{ x: vars[0], y: vars[1], value: 0.5 }];
      render(<HeatmapCorrelation data={data} variables={vars} />);
      expect(screen.getByText(/Showing correlation matrix capped at 50x50 variables/i)).toBeInTheDocument();
    });
  });

  describe("ScatterCluster", () => {
    it("renders gracefully with empty data", () => {
      render(<ScatterCluster data={undefined} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders gracefully with empty points array", () => {
      render(<ScatterCluster data={{ points: [] } as any} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders correctly with data", () => {
      const data = {
        points: [{ x: 1, y: 2, clusterId: 0 }],
        clusterCount: 1,
        outlierMask: [false],
        outlierScoreMethod: "isolation_forest" as const,
      };
      render(<ScatterCluster data={data} />);
      expect(screen.getByTestId("recharts-scatter-chart")).toBeInTheDocument();
    });
  });

  describe("BoxPlot", () => {
    it("renders gracefully with empty data", () => {
      render(<BoxPlot data={[]} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders gracefully with undefined data", () => {
      render(<BoxPlot data={undefined} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("renders correctly with data", () => {
      const data = [
        { category: "A", min: 0, q1: 1, median: 2, q3: 3, max: 4 }
      ];
      render(<BoxPlot data={data} />);
      expect(screen.getByTestId("recharts-bar-chart")).toBeInTheDocument();
    });
  });
});
