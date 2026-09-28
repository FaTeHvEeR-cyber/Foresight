import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ErrorBar
} from 'recharts';
import type { HypothesisResponse } from '@/types/api';

// Extends hypothesis response based on Agent 1's contract (ENDPOINT_CONTRACT_PHASE4.md)
interface ExtendedHypothesisResponse extends HypothesisResponse {
  tests?: Array<{
    group_stats: Array<{
      group: string;
      mean: number;
      std: number;
      n: number;
    }>;
  }>;
}

interface BarComparisonProps {
  data?: ExtendedHypothesisResponse | any;
}

export function BarComparison({ data }: BarComparisonProps) {
  if (!data) return <div data-testid="chart-bar_comparison">No data available</div>;

  let chartData: any[] = [];

  // Try to extract from tests[0].group_stats
  if (data.tests && data.tests.length > 0 && data.tests[0].group_stats) {
    chartData = data.tests[0].group_stats.map((stat: any) => ({
      group: stat.group,
      mean: stat.mean ?? 0,
      errorY: stat.std ? [stat.mean - stat.std, stat.mean + stat.std] : undefined
    }));
  } else if (data.groups && Array.isArray(data.groups)) {
    // Fallback if only groups array is provided
    chartData = data.groups.map((group: string) => ({
      group,
      mean: 0
    }));
  } else if (Array.isArray(data)) {
    // Handle plain array format
    chartData = data.map((item: any, idx: number) => ({
      group: item.group ?? `Group ${idx}`,
      mean: item.mean ?? item.value ?? 0,
      errorY: item.std ? [item.mean - item.std, item.mean + item.std] : undefined
    }));
  }

  if (chartData.length === 0) {
    return <div data-testid="chart-bar_comparison">No data available</div>;
  }

  return (
    <div data-testid="chart-bar_comparison" style={{ width: '100%', height: 400 }}>
      <ResponsiveContainer>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="group" />
          <YAxis />
          <Tooltip />
          <Legend />
          <Bar dataKey="mean" fill="#3b82f6" isAnimationActive={false}>
             {chartData.some(d => d.errorY) && <ErrorBar dataKey="errorY" width={4} strokeWidth={2} stroke="#1e3a8a" />}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
