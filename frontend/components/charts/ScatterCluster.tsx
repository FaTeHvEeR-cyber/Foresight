"use client";

import React, { useMemo } from "react";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ZAxis,
  Cell,
} from "recharts";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { SegmentationResponse } from "../../types/api";

function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

// Simple color palette for clusters
const CLUSTER_COLORS = [
  "#3b82f6", // blue
  "#ef4444", // red
  "#10b981", // green
  "#f59e0b", // yellow
  "#8b5cf6", // purple
  "#ec4899", // pink
  "#14b8a6", // teal
  "#f97316", // orange
];

interface ScatterClusterProps {
  data?: SegmentationResponse;
  className?: string;
  xAxisLabel?: string;
  yAxisLabel?: string;
}

export function ScatterCluster({ data, className, xAxisLabel = "X", yAxisLabel = "Y" }: ScatterClusterProps) {
  if (!data || !data.points || data.points.length === 0) {
    return (
      <div className={cn("flex h-64 items-center justify-center rounded-lg border bg-muted/10 text-muted-foreground", className)}>
        No segmentation data available.
      </div>
    );
  }

  // Pre-process points to add color information directly (for Recharts ease)
  const chartData = useMemo(() => {
    return data.points.map((pt, i) => ({
      x: pt.x,
      y: pt.y,
      clusterId: pt.clusterId,
      isOutlier: data.outlierMask?.[i] || false,
    }));
  }, [data]);

  return (
    <div className={cn("h-[400px] w-full border rounded-lg p-4 bg-background", className)}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
          <XAxis type="number" dataKey="x" name={xAxisLabel} tick={{ fontSize: 12 }} />
          <YAxis type="number" dataKey="y" name={yAxisLabel} tick={{ fontSize: 12 }} />
          <ZAxis type="number" range={[50, 50]} />
          <Tooltip 
            cursor={{ strokeDasharray: '3 3' }} 
            contentStyle={{ borderRadius: '8px', fontSize: '12px' }}
          />
          <Scatter name="Clusters" data={chartData}>
            {chartData.map((entry, index) => {
              const color = entry.isOutlier 
                ? "#000000" // Black for outliers
                : CLUSTER_COLORS[entry.clusterId % CLUSTER_COLORS.length];
              return <Cell key={`cell-${index}`} fill={color} />;
            })}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
