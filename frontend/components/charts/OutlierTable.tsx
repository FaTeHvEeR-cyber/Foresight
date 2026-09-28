import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

interface OutlierData {
  id: string | number;
  [key: string]: string | number;
}

interface OutlierTableProps {
  data?: OutlierData[];
  columns?: string[];
  maxRows?: number;
  className?: string;
}

export function OutlierTable({ data = [], columns = [], maxRows = 100, className }: OutlierTableProps) {
  if (!data || !Array.isArray(data) || data.length === 0) {
    return (
      <div
        data-testid="chart-outlier_table"
        className={cn("p-4 border rounded-lg text-center text-muted-foreground flex items-center justify-center min-h-[140px]", className)}
      >
        No data available
      </div>
    );
  }

  // Cap rows to handle large inputs without freezing
  const cappedData = data.slice(0, maxRows);
  const isCapped = data.length > maxRows;

  // Infer columns if not provided
  const cols = columns.length > 0 ? columns : Object.keys(data[0] || {}).filter((k) => k !== "id");

  return (
    <div data-testid="chart-outlier_table" className={cn("border rounded-lg overflow-hidden flex flex-col", className)}>
      <div className="overflow-x-auto max-h-[400px]">
        <table className="w-full text-sm text-left">
          <thead className="text-xs uppercase bg-muted/50 sticky top-0">
            <tr>
              <th className="px-4 py-3 font-medium">ID</th>
              {cols.map((col) => (
                <th key={col} className="px-4 py-3 font-medium">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y">
            {cappedData.map((row, i) => (
              <tr key={row.id || i} className="hover:bg-muted/50">
                <td className="px-4 py-3 font-medium">{row.id}</td>
                {cols.map((col) => (
                  <td key={col} className="px-4 py-3">
                    {row[col]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {isCapped && (
        <div className="p-2 text-xs text-center bg-muted/20 text-muted-foreground border-t">
          Showing first {maxRows} out of {data.length} outliers. Cap chosen to preserve page performance.
        </div>
      )}
    </div>
  );
}
