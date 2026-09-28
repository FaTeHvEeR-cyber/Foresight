import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

interface KpiCardProps {
  title?: string;
  value?: string | number | null;
  icon?: React.ReactNode;
  description?: string;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  className?: string;
  data?: any;
}

export function KpiCard({ title = "KPI", value, icon, description, trend, className, data }: KpiCardProps) {
  const displayValue = value ?? data?.value ?? data?.message ?? null;
  const displayTitle = title || data?.title || "KPI";

  if (displayValue === undefined || displayValue === null || displayValue === "") {
    return (
      <div
        data-testid="chart-kpi_card"
        className={cn("rounded-lg border bg-card text-card-foreground shadow-sm p-6 opacity-50 flex flex-col items-center justify-center min-h-[140px]", className)}
      >
        <h3 className="tracking-tight text-sm font-medium text-muted-foreground">{displayTitle}</h3>
        <p className="mt-2 text-2xl font-bold">--</p>
        <span className="text-xs text-muted-foreground mt-1">No data available</span>
      </div>
    );
  }

  return (
    <div data-testid="chart-kpi_card" className={cn("rounded-lg border bg-card text-card-foreground shadow-sm p-6", className)}>
      <div className="flex flex-row items-center justify-between space-y-0 pb-2">
        <h3 className="tracking-tight text-sm font-medium text-muted-foreground">{displayTitle}</h3>
        {icon && <div className="h-4 w-4 text-muted-foreground">{icon}</div>}
      </div>
      <div className="flex flex-col">
        <div className="text-2xl font-bold">{displayValue}</div>
        {(description || trend) && (
          <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
            {trend && (
              <span className={trend.isPositive ? "text-green-500" : "text-red-500"}>
                {trend.isPositive ? "+" : "-"}{Math.abs(trend.value)}%
              </span>
            )}
            {description && <span>{description}</span>}
          </p>
        )}
      </div>
    </div>
  );
}
