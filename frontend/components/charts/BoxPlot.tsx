"use client";

import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { HypothesisResponse } from "@/types/api";

function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

export interface BoxPlotData {
  category: string;
  min: number;
  q1: number;
  median: number;
  q3: number;
  max: number;
  outliers?: number[];
  group?: string;
}

interface BoxPlotProps {
  data?: BoxPlotData[] | HypothesisResponse | any;
  className?: string;
}

// Custom shape to draw the box plot over a standard bar
const BoxPlotShape = (props: any) => {
  const { x, y, width, height, min, q1, median, q3, max, payload, yAxis } = props;
  
  if (!yAxis) return null;
  
  // Calculate y coordinates based on the yAxis scale
  const scale = yAxis.scale;
  const yMin = scale(payload.min);
  const yQ1 = scale(payload.q1);
  const yMedian = scale(payload.median);
  const yQ3 = scale(payload.q3);
  const yMax = scale(payload.max);

  const centerX = x + width / 2;
  const boxWidth = width * 0.6;
  const halfBox = boxWidth / 2;

  return (
    <g>
      {/* Min to Max line (Whisker) */}
      <line x1={centerX} y1={yMin} x2={centerX} y2={yMax} stroke="#8884d8" strokeWidth={2} />
      {/* Top Cap (Max) */}
      <line x1={centerX - halfBox / 2} y1={yMax} x2={centerX + halfBox / 2} y2={yMax} stroke="#8884d8" strokeWidth={2} />
      {/* Bottom Cap (Min) */}
      <line x1={centerX - halfBox / 2} y1={yMin} x2={centerX + halfBox / 2} y2={yMin} stroke="#8884d8" strokeWidth={2} />
      {/* The Box (Q1 to Q3) */}
      <rect x={centerX - halfBox} y={yQ3} width={boxWidth} height={Math.abs(yQ1 - yQ3)} fill="#8884d8" fillOpacity={0.5} stroke="#8884d8" strokeWidth={2} />
      {/* Median Line */}
      <line x1={centerX - halfBox} y1={yMedian} x2={centerX + halfBox} y2={yMedian} stroke="#000" strokeWidth={2} />
      
      {/* Outliers */}
      {payload.outliers?.map((outlierVal: number, i: number) => {
        const yOutlier = scale(outlierVal);
        return <circle key={i} cx={centerX} cy={yOutlier} r={3} fill="#ef4444" />;
      })}
    </g>
  );
};

export function BoxPlot({ data, className }: BoxPlotProps) {
  let rawList: any[] = [];
  if (data?.tests && Array.isArray(data.tests) && data.tests.length > 0 && Array.isArray(data.tests[0].group_stats)) {
    rawList = data.tests[0].group_stats;
  } else if (Array.isArray(data)) {
    rawList = data;
  }

  // Filter and map to ensure valid BoxPlotData with category and numeric min/q1/median/q3/max
  const chartData: BoxPlotData[] = rawList
    .filter(
      (d) =>
        d &&
        typeof d === "object" &&
        (typeof d.category === "string" || typeof d.group === "string" || d.category || d.group) &&
        typeof d.min === "number" &&
        !isNaN(d.min) &&
        typeof d.q1 === "number" &&
        !isNaN(d.q1) &&
        typeof d.median === "number" &&
        !isNaN(d.median) &&
        typeof d.q3 === "number" &&
        !isNaN(d.q3) &&
        typeof d.max === "number" &&
        !isNaN(d.max)
    )
    .map((d, i) => ({
      category: String(d.category ?? d.group ?? `Group ${i + 1}`),
      min: d.min,
      q1: d.q1,
      median: d.median,
      q3: d.q3,
      max: d.max,
      outliers: Array.isArray(d.outliers) ? d.outliers : undefined,
    }));

  if (chartData.length === 0) {
    return (
      <div
        data-testid="chart-box_plot"
        className={cn("flex h-64 items-center justify-center rounded-lg border bg-muted/10 text-muted-foreground", className)}
      >
        No data available
      </div>
    );
  }

  // Find overall min and max to set domain properly
  const yDomainMin = Math.min(...chartData.map((d) => Math.min(d.min, ...(d.outliers || []))));
  const yDomainMax = Math.max(...chartData.map((d) => Math.max(d.max, ...(d.outliers || []))));

  return (
    <div data-testid="chart-box_plot" className={cn("h-[400px] w-full border rounded-lg p-4 bg-background", className)}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
          <XAxis dataKey="category" tick={{ fontSize: 12 }} />
          <YAxis type="number" domain={[yDomainMin, yDomainMax]} tick={{ fontSize: 12 }} />
          <Tooltip 
            cursor={{ fill: 'rgba(0, 0, 0, 0.05)' }}
            content={({ active, payload }) => {
              if (active && payload && payload.length) {
                const d = payload[0].payload;
                return (
                  <div className="bg-background border rounded-lg p-2 shadow-sm text-xs">
                    <p className="font-bold mb-1">{d.category}</p>
                    <p>Max: {d.max}</p>
                    <p>Q3: {d.q3}</p>
                    <p>Median: {d.median}</p>
                    <p>Q1: {d.q1}</p>
                    <p>Min: {d.min}</p>
                  </div>
                );
              }
              return null;
            }}
          />
          {/* We use Bar with a custom shape, dataKey can be anything (using 'max' to ensure it scales correctly conceptually, but the shape uses the full payload) */}
          <Bar dataKey="max" shape={<BoxPlotShape />} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
