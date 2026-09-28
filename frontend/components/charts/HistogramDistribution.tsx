import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';

interface HistogramDistributionProps {
  data?: any; // Expecting bins and frequencies or just actuals
}

export function HistogramDistribution({ data }: HistogramDistributionProps) {
  let chartData: any[] = [];
  
  if (data?.bins && data?.frequencies) {
    chartData = data.bins.map((bin: number | string, idx: number) => ({
      bin: String(bin),
      count: data.frequencies[idx] ?? 0
    }));
  } else if (data?.actuals && Array.isArray(data.actuals)) {
    // Basic fallback: just show the actuals as bars if no bins provided
    chartData = data.actuals.slice(0, 50).map((val: number, idx: number) => ({
      bin: `Item ${idx}`,
      count: val
    }));
  } else if (Array.isArray(data)) {
    chartData = data;
  }

  if (!chartData || chartData.length === 0) {
    return <div data-testid="chart-histogram_distribution">No data available</div>;
  }

  return (
    <div data-testid="chart-histogram_distribution" style={{ width: '100%', height: 400 }}>
      <ResponsiveContainer>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="bin" />
          <YAxis />
          <Tooltip />
          <Bar dataKey="count" fill="#6366f1" isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
