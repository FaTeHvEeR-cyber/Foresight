import React from 'react';
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import type { ForecastResponse } from '@/types/api';

interface ForecastBandChartProps {
  data?: ForecastResponse & { lower?: number[]; upper?: number[] };
}

export function ForecastBandChart({ data }: ForecastBandChartProps) {
  if (!data || !data.dates || data.dates.length === 0) {
    return <div data-testid="chart-forecast_band_chart">No data available</div>;
  }

  const chartData = data.dates.map((date, idx) => {
    const actual = data.actuals?.[idx] ?? null;
    const forecast = data.forecasts?.[idx] ?? null;
    const lower = data.lower?.[idx] ?? null;
    const upper = data.upper?.[idx] ?? null;
    // For recharts Area chart band
    const band = (lower !== null && upper !== null && !isNaN(lower) && !isNaN(upper)) ? [lower, upper] : null;
    return {
      date,
      actual,
      forecast,
      band
    };
  });

  return (
    <div data-testid="chart-forecast_band_chart" style={{ width: '100%', height: 400 }}>
      <ResponsiveContainer>
        <ComposedChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <Legend />
          <Area type="monotone" dataKey="band" fill="#0d9488" stroke="none" fillOpacity={0.2} isAnimationActive={false} />
          <Line type="monotone" dataKey="actual" stroke="#2563eb" dot={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="forecast" stroke="#0d9488" strokeDasharray="5 5" dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
