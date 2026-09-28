import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

interface HeatmapCorrelationProps {
  data?: {
    x: string;
    y: string;
    value: number; // -1 to 1
  }[];
  variables?: string[];
  maxVars?: number;
  className?: string;
}

export function HeatmapCorrelation({ data = [], variables = [], maxVars = 50, className }: HeatmapCorrelationProps) {
  if (!data || data.length === 0) {
    return (
      <div className={cn("p-4 border rounded-lg text-center text-muted-foreground flex items-center justify-center min-h-[200px]", className)}>
        No correlation data available.
      </div>
    );
  }

  // Cap variables
  const vars = variables.length > 0
    ? variables.slice(0, maxVars)
    : Array.from(new Set(data.map((d) => d.x))).slice(0, maxVars);
  
  const isCapped = variables.length > maxVars || (variables.length === 0 && new Set(data.map(d => d.x)).size > maxVars);

  const getCellColor = (value: number) => {
    // Red for negative, Blue for positive
    if (value < 0) {
      const alpha = Math.abs(value);
      return `rgba(239, 68, 68, ${alpha})`; // red-500
    }
    const alpha = value;
    return `rgba(59, 130, 246, ${alpha})`; // blue-500
  };

  const getMapValue = (x: string, y: string) => {
    const item = data.find((d) => d.x === x && d.y === y);
    return item ? item.value : 0;
  };

  return (
    <div className={cn("flex flex-col border rounded-lg overflow-hidden", className)}>
      <div className="overflow-auto max-h-[500px]">
        <div 
          className="grid gap-[1px] bg-muted/20" 
          style={{ gridTemplateColumns: `auto repeat(${vars.length}, minmax(40px, 1fr))` }}
        >
          {/* Top Header */}
          <div className="bg-background sticky top-0 left-0 z-20"></div>
          {vars.map((v) => (
            <div key={`header-x-${v}`} className="bg-background sticky top-0 z-10 p-2 text-xs font-medium rotate-[-45deg] origin-bottom-left text-ellipsis whitespace-nowrap h-24 flex items-end">
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
