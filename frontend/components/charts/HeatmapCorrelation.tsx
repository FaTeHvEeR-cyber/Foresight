import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

export interface HeatmapPoint {
  x: string;
  y: string;
  value: number; // -1 to 1
}

export interface HeatmapCorrelationProps {
  data?: HeatmapPoint[];
  variables?: string[];
  maxVars?: number;
  className?: string;
}

export function HeatmapCorrelation({
  data = [],
  variables = [],
  maxVars = 50,
  className,
}: HeatmapCorrelationProps) {
  // Validate array input
  if (!data || !Array.isArray(data) || data.length === 0) {
    return (
      <div
        data-testid="chart-heatmap_correlation"
        className={cn(
          "p-4 border rounded-lg text-center text-muted-foreground flex items-center justify-center min-h-[200px]",
          className
        )}
      >
        No data available
      </div>
    );
  }

  // Filter valid data points to prevent crashes on malformed data
  const validData = data.filter(
    (d) =>
      d &&
      typeof d === "object" &&
      typeof d.x === "string" &&
      typeof d.y === "string" &&
      typeof d.value === "number" &&
      !isNaN(d.value)
  );

  if (validData.length === 0) {
    return (
      <div
        data-testid="chart-heatmap_correlation"
        className={cn(
          "p-4 border rounded-lg text-center text-muted-foreground flex items-center justify-center min-h-[200px]",
          className
        )}
      >
        No data available
      </div>
    );
  }

  // Cap variables safely
  const safeVariables = Array.isArray(variables) ? variables.filter((v) => typeof v === "string") : [];
  const derivedVars = Array.from(new Set(validData.map((d) => d.x)));
  const baseVars = safeVariables.length > 0 ? safeVariables : derivedVars;
  const vars = baseVars.slice(0, maxVars);

  if (vars.length === 0) {
    return (
      <div
        data-testid="chart-heatmap_correlation"
        className={cn(
          "p-4 border rounded-lg text-center text-muted-foreground flex items-center justify-center min-h-[200px]",
          className
        )}
      >
        No data available
      </div>
    );
  }

  const isCapped = baseVars.length > maxVars;

  const getCellColor = (value: number) => {
    if (typeof value !== "number" || isNaN(value)) return "transparent";
    // Red for negative, Blue for positive
    if (value < 0) {
      const alpha = Math.min(Math.abs(value), 1);
      return `rgba(239, 68, 68, ${alpha})`; // red-500
    }
    const alpha = Math.min(value, 1);
    return `rgba(59, 130, 246, ${alpha})`; // blue-500
  };

  const getMapValue = (x: string, y: string) => {
    const item = validData.find((d) => d.x === x && d.y === y);
    return item && typeof item.value === "number" && !isNaN(item.value) ? item.value : 0;
  };

  return (
    <div
      data-testid="chart-heatmap_correlation"
      className={cn("flex flex-col border rounded-lg overflow-hidden", className)}
    >
      <div className="overflow-auto max-h-[500px]">
        <div
          className="grid gap-[1px] bg-muted/20"
          style={{ gridTemplateColumns: `auto repeat(${vars.length}, minmax(40px, 1fr))` }}
        >
          {/* Top Header */}
          <div className="bg-background sticky top-0 left-0 z-20"></div>
          {vars.map((v) => (
            <div
              key={`header-x-${v}`}
              className="bg-background sticky top-0 z-10 p-2 text-xs font-medium rotate-[-45deg] origin-bottom-left text-ellipsis whitespace-nowrap h-24 flex items-end"
            >
              {v}
            </div>
          ))}

          {/* Rows */}
          {vars.map((yVar) => (
            <React.Fragment key={`row-${yVar}`}>
              {/* Row Header */}
              <div className="bg-background sticky left-0 z-10 p-2 text-xs font-medium flex items-center text-ellipsis overflow-hidden whitespace-nowrap">
                {yVar}
              </div>
              {/* Cells */}
              {vars.map((xVar) => {
                const val = getMapValue(xVar, yVar);
                return (
                  <div
                    key={`cell-${xVar}-${yVar}`}
                    className="aspect-square flex items-center justify-center text-[10px] sm:text-xs text-white tooltip-trigger"
                    style={{ backgroundColor: getCellColor(val) }}
                    title={`${xVar} vs ${yVar}: ${val.toFixed(2)}`}
                  >
                    {Math.abs(val) > 0.3 ? val.toFixed(1) : ""}
                  </div>
                );
              })}
            </React.Fragment>
          ))}
        </div>
      </div>
      {isCapped && (
        <div className="p-2 text-xs text-center bg-muted/20 text-muted-foreground border-t">
          Showing correlation matrix capped at {maxVars}x{maxVars} variables to preserve page performance.
        </div>
      )}
    </div>
  );
}
