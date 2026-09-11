"use client";

import React from "react";
import {
  FileSpreadsheet,
  FileText,
  Trash2,
  Play,
  Loader2,
  CheckCircle2,
  HardDrive,
  FileCode,
} from "lucide-react";
import type { DetectedFileKind, DetectedFormat } from "@/types/api";

export interface StagedFileCardProps {
  file: File;
  detectedKind: DetectedFileKind;
  detectedFormat: DetectedFormat;
  isAnalyzing: boolean;
  isAnalyzed?: boolean;
  onRemove: () => void;
  onAnalyze: () => void;
}

export function StagedFileCard({
  file,
  detectedKind,
  detectedFormat,
  isAnalyzing,
  isAnalyzed = false,
  onRemove,
  onAnalyze,
}: StagedFileCardProps) {
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    const mb = kb / 1024;
    return `${mb.toFixed(2)} MB`;
  };

  const getFormatBadgeColor = (format: DetectedFormat) => {
    switch (format) {
      case "csv":
      case "tsv":
        return "bg-emerald-950/60 text-emerald-300 border-emerald-600/40";
      case "xlsx":
      case "xls":
      case "parquet":
        return "bg-green-950/60 text-green-300 border-green-600/40";
      case "pdf":
        return "bg-rose-950/60 text-rose-300 border-rose-600/40";
      case "docx":
      case "txt":
      case "md":
        return "bg-cyan-950/60 text-cyan-300 border-cyan-600/40";
      default:
        return "bg-slate-800 text-slate-300 border-slate-700";
    }
  };

  const isTabular = detectedKind === "tabular";

  return (
    <div className="w-full rounded-2xl glass-panel p-5 md:p-6 shadow-xl border border-slate-700/80 transition-all duration-300">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        {/* Left Section: File Icon + Details */}
        <div className="flex items-start sm:items-center gap-4 min-w-0">
          <div
            className={`w-14 h-14 rounded-xl flex items-center justify-center flex-shrink-0 border ${
              isTabular
                ? "bg-emerald-950/40 border-emerald-700/40 text-emerald-400"
                : "bg-cyan-950/40 border-cyan-700/40 text-cyan-400"
            }`}
          >
            {isTabular ? (
              <FileSpreadsheet className="w-7 h-7" />
            ) : detectedFormat === "pdf" ? (
              <FileText className="w-7 h-7 text-rose-400" />
            ) : (
              <FileCode className="w-7 h-7" />
            )}
          </div>

          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-base font-semibold text-white truncate max-w-xs md:max-w-md">
                {file.name}
              </span>
              <span
                className={`text-[11px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider border ${getFormatBadgeColor(
                  detectedFormat
                )}`}
              >
                .{detectedFormat}
              </span>
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-slate-800/90 text-slate-300 border border-slate-700">
                {isTabular ? "Tabular Dataset" : "Document Report"}
              </span>
            </div>

            <div className="flex items-center gap-3 text-xs text-slate-400">
              <span className="inline-flex items-center gap-1">
                <HardDrive className="w-3.5 h-3.5 text-slate-500" />
                {formatFileSize(file.size)}
              </span>
              <span>•</span>
              {isAnalyzed ? (
                <span className="inline-flex items-center gap-1 text-emerald-400 font-medium">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Analysis Ready
                </span>
              ) : isAnalyzing ? (
                <span className="inline-flex items-center gap-1 text-blue-400 font-medium">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Processing Engines...
                </span>
              ) : (
                <span className="text-amber-400/90 font-medium">Staged (In-Memory)</span>
              )}
            </div>
          </div>
        </div>

        {/* Right Section: Actions */}
        <div className="flex items-center gap-3 self-end sm:self-center">
          <button
            type="button"
            onClick={onRemove}
            disabled={isAnalyzing}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-medium text-slate-400 hover:text-red-400 hover:bg-red-950/30 border border-transparent hover:border-red-800/40 transition-colors disabled:opacity-50 disabled:pointer-events-none"
            title="Remove staged file"
          >
            <Trash2 className="w-4 h-4" />
            <span>Remove</span>
          </button>

          <button
            type="button"
            onClick={onAnalyze}
            disabled={isAnalyzing}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs md:text-sm font-semibold text-white bg-blue-600 hover:bg-blue-500 active:bg-blue-700 shadow-lg shadow-blue-600/30 transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isAnalyzing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Analyzing Engines...</span>
              </>
            ) : isAnalyzed ? (
              <>
                <Play className="w-4 h-4 fill-current" />
                <span>Re-run Analysis</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" />
                <span>Analyze with Foresight</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
