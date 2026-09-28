import React from 'react';
import { LineChart as RechartsLineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import type { ForecastResponse } from '@/types/api';

interface LineChartProps {
  data?: ForecastResponse;
}

export function LineChart({ data }: LineChartProps) {
  if (!data || !data.dates || data.dates.length === 0) {
    return <div data-testid="chart-line_chart">No data available</div>;
  }

  const chartData = data.dates.map((date, idx) => ({
    date,
    actual: data.actuals?.[idx] ?? null,
    forecast: data.forecasts?.[idx] ?? null,
  }));

  return (
    <div data-testid="chart-line_chart" style={{ width: '100%', height: 400 }}>
      <ResponsiveContainer>
        <RechartsLineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="actual" stroke="#2563eb" dot={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="forecast" stroke="#0d9488" strokeDasharray="5 5" dot={false} isAnimationActive={false} />
        </RechartsLineChart>
      </ResponsiveContainer>
    </div>
  );
}

