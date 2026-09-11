"use client";

import React, { useState, useRef, useCallback } from "react";
import { UploadCloud, FileSpreadsheet, FileText, AlertCircle, Sparkles } from "lucide-react";
import type { DetectedFileKind, DetectedFormat } from "@/types/api";

export const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB in-memory guard

export const ACCEPTED_EXTENSIONS: Record<string, { detectedKind: DetectedFileKind; detectedFormat: DetectedFormat }> = {
  // Tabular
  csv: { detectedKind: "tabular", detectedFormat: "csv" },
  tsv: { detectedKind: "tabular", detectedFormat: "tsv" },
  xlsx: { detectedKind: "tabular", detectedFormat: "xlsx" },
  xls: { detectedKind: "tabular", detectedFormat: "xls" },
  parquet: { detectedKind: "tabular", detectedFormat: "parquet" },

  // Document
  pdf: { detectedKind: "document", detectedFormat: "pdf" },
  docx: { detectedKind: "document", detectedFormat: "docx" },
  txt: { detectedKind: "document", detectedFormat: "txt" },
  md: { detectedKind: "document", detectedFormat: "md" },
};

export interface MultiFormatDropzoneProps {
  onFileAccepted: (
    file: File,
    metadata: { detectedKind: DetectedFileKind; detectedFormat: DetectedFormat }
  ) => void;
  onError?: (errorMessage: string) => void;
  disabled?: boolean;
}

export function MultiFormatDropzone({
  onFileAccepted,
  onError,
  disabled = false,
}: MultiFormatDropzoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const parseFileMetadata = (file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    return ACCEPTED_EXTENSIONS[ext] || null;
  };

  const validateAndProcessFile = useCallback(
    (file: File) => {
      setLocalError(null);

      // 1. 25MB Guard
      if (file.size > MAX_FILE_SIZE_BYTES) {
        const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
        const err = `File exceeds the 25MB safety boundary (${sizeMb} MB). Foresight processes up to 25MB in-memory per run.`;
        setLocalError(err);
        onError?.(err);
        return;
      }

      // 2. Format & Kind detection
      const meta = parseFileMetadata(file);
      if (!meta) {
        const ext = file.name.split(".").pop() || "unknown";
        const err = `Unsupported file format (.${ext}). Foresight accepts CSV, TSV, XLSX, XLS, PARQUET, PDF, DOCX, TXT, and MD.`;
        setLocalError(err);
        onError?.(err);
        return;
      }

      onFileAccepted(file, meta);
    },
    [onFileAccepted, onError]
  );

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    if (disabled) return;

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      validateAndProcessFile(files[0]);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      validateAndProcessFile(files[0]);
      // Reset input value so the same file can be selected again if needed
      e.target.value = "";
    }
  };

  const handleBrowseClick = () => {
    if (disabled) return;
    fileInputRef.current?.click();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleBrowseClick();
    }
  };

  return (
    <div className="w-full space-y-3">
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        onClick={handleBrowseClick}
        onKeyDown={handleKeyDown}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`relative w-full rounded-2xl p-8 md:p-12 text-center cursor-pointer transition-all duration-300 select-none border-2 border-dashed ${
          isDragOver
            ? "border-blue-500 bg-blue-950/30 scale-[1.008] shadow-[0_0_30px_rgba(59,130,246,0.25)]"
            : "border-slate-700/80 bg-slate-900/40 hover:border-slate-500 hover:bg-slate-900/70"
        } ${disabled ? "opacity-50 cursor-not-allowed pointer-events-none" : ""}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".csv,.tsv,.xlsx,.xls,.parquet,.pdf,.docx,.txt,.md"
          onChange={handleFileInputChange}
          disabled={disabled}
        />

        <div className="flex flex-col items-center justify-center space-y-4">
          {/* Icon Badge */}
          <div
            className={`w-16 h-16 rounded-2xl flex items-center justify-center transition-transform duration-300 ${
              isDragOver
                ? "bg-blue-600 text-white scale-110 shadow-lg shadow-blue-500/40"
                : "bg-slate-800/90 text-blue-400 border border-slate-700/70 group-hover:scale-105"
            }`}
          >
            <UploadCloud className="w-8 h-8" />
          </div>

          {/* Heading & Instructions */}
          <div className="space-y-1.5 max-w-lg">
            <h3 className="text-lg md:text-xl font-semibold text-white tracking-tight">
              {isDragOver ? "Drop your file to stage for analysis" : "Drag & drop files, or browse"}
            </h3>
            <p className="text-sm text-slate-400">
              Drop tabular datasets for forecasting & clustering, or documents for offline NLP summarization.
            </p>
          </div>

          {/* Supported Formats Strips */}
          <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-800/80 border border-slate-700/60 text-xs font-medium text-slate-300">
              <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
              <span>Tabular:</span>
              <span className="text-emerald-400">CSV, TSV, XLSX, XLS, Parquet</span>
            </div>

            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-800/80 border border-slate-700/60 text-xs font-medium text-slate-300">
              <FileText className="w-3.5 h-3.5 text-cyan-400" />
              <span>Document:</span>
              <span className="text-cyan-400">PDF, DOCX, TXT, MD</span>
            </div>

            <div className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-950/40 border border-amber-600/30 text-xs font-medium text-amber-300">
              <Sparkles className="w-3 h-3 text-amber-400" />
              <span>Max 25MB Guard</span>
            </div>
          </div>
        </div>
      </div>

      {/* Error message banner */}
      {localError && (
        <div className="flex items-start gap-3 p-3.5 rounded-xl bg-red-950/50 border border-red-800/60 text-red-200 text-sm animate-in fade-in duration-200">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold text-red-300">Validation Error</p>
            <p className="text-red-300/90 text-xs mt-0.5">{localError}</p>
          </div>
        </div>
      )}
    </div>
  );
}
