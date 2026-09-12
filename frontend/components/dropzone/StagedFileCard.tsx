"use client";

import React from "react";
import { CheckCircle2 } from "lucide-react";
import type { DetectedFileKind, DetectedFormat } from "@/types/api";

export interface StagedFileCardProps {
  fileName?: string;
  fileSizeLabel?: string;
  formatBadge?: string;
  onClear?: () => void;
  onAnalyze?: () => void;

  // Optional props for backward-compatibility with existing views
  file?: File;
  detectedKind?: DetectedFileKind;
  detectedFormat?: DetectedFormat;
  isAnalyzing?: boolean;
  isAnalyzed?: boolean;
  onRemove?: () => void;
  className?: string;
}

export function StagedFileCard({
  fileName,
  fileSizeLabel,
  formatBadge,
  onClear,
  onAnalyze,
  file,
  isAnalyzing = false,
  onRemove,
  className = "",
}: StagedFileCardProps) {
  // Resolve values prioritizing explicit props, then falling back to File object
  const resolvedFileName = fileName || file?.name || "Uploaded file";

  const resolvedFormatBadge =
    formatBadge ||
    (file ? file.name.split(".").pop()?.toUpperCase() : "FILE") ||
    "FILE";

  const resolvedFileSizeLabel =
    fileSizeLabel ||
    (file
      ? file.size < 1024
        ? `${file.size} B`
        : file.size < 1024 * 1024
        ? `${(file.size / 1024).toFixed(1)} KB`
        : `${(file.size / (1024 * 1024)).toFixed(2)} MB`
      : "Unknown size");

  const handleClear = () => {
    if (onClear) {
      onClear();
    } else if (onRemove) {
      onRemove();
    }
  };

  const handleAnalyze = () => {
    onAnalyze?.();
  };

  return (
    <div
      className={`w-full rounded-2xl bg-white p-5 md:p-6 shadow-sm border border-slate-200 transition-all duration-200 ${className}`}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        {/* Left Section: Green checkmark icon + file info */}
        <div className="flex items-start sm:items-center gap-3.5 min-w-0">
          <div className="w-10 h-10 rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center flex-shrink-0">
            <CheckCircle2 className="w-6 h-6 text-emerald-600" aria-hidden="true" />
          </div>

          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="text-base font-semibold text-slate-900 truncate max-w-xs md:max-w-md"
                title={resolvedFileName}
              >
                {resolvedFileName}
              </span>
              <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200 uppercase tracking-wide">
                {resolvedFormatBadge}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span>{resolvedFileSizeLabel}</span>
              <span className="text-slate-300">•</span>
              <span className="inline-flex items-center text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200 font-medium">
                Ready for analysis
              </span>
            </div>
          </div>
        </div>

        {/* Right Section: Actions */}
        <div className="flex items-center gap-3 self-end sm:self-center flex-shrink-0">
          <button
            type="button"
            onClick={handleClear}
            className="px-3.5 py-2 text-xs sm:text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 active:bg-slate-300 rounded-xl transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2"
          >
            Clear / Replace
          </button>

          <button
            type="button"
            onClick={handleAnalyze}
            disabled={isAnalyzing}
            className="px-5 py-2.5 text-xs sm:text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 active:bg-blue-800 rounded-xl shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            Analyze & Generate
          </button>
        </div>
      </div>
    </div>
  );
}
