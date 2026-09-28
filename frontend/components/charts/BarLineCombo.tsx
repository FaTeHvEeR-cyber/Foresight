import React from 'react';
import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';

interface BarLineComboProps {
  data?: any;
}

export function BarLineCombo({ data }: BarLineComboProps) {
  let chartData: any[] = [];

  if (data && data.dates && data.dates.length > 0) {
    chartData = data.dates.map((date: string, idx: number) => ({
      date,
      barValue: data.actuals?.[idx] ?? null,
      lineValue: data.forecasts?.[idx] ?? null,
    }));
  } else if (Array.isArray(data)) {
    chartData = data;
  }

  if (chartData.length === 0) {
    return <div data-testid="chart-bar_line_combo">No data available</div>;
  }

  return (
    <div data-testid="chart-bar_line_combo" style={{ width: '100%', height: 400 }}>
      <ResponsiveContainer>
        <ComposedChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={data?.dates ? "date" : "name"} />
          <YAxis />
          <Tooltip />
          <Legend />
          <Bar dataKey="barValue" fill="#3b82f6" isAnimationActive={false} />
          <Line type="monotone" dataKey="lineValue" stroke="#10b981" strokeWidth={2} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
