"use client";

import React, { useState, useRef, useCallback } from "react";
import { UploadCloud, AlertCircle } from "lucide-react";
import { StagedFileCard } from "./StagedFileCard";
import type { DetectedFileKind, DetectedFormat } from "@/types/api";

export const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB hard limit

export const ACCEPTED_EXTENSIONS = [
  "csv",
  "tsv",
  "xlsx",
  "xls",
  "parquet",
  "pdf",
  "docx",
  "txt",
  "md",
] as const;

export const ACCEPTED_EXTENSIONS_MAP: Record<
  string,
  { detectedKind: DetectedFileKind; detectedFormat: DetectedFormat }
> = {
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

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  return `${mb.toFixed(2)} MB`;
}

export function getFormatBadge(fileName: string): string {
  const ext = fileName.split(".").pop()?.toLowerCase();
  return ext ? ext.toUpperCase() : "FILE";
}

export interface MultiFormatDropzoneProps {
  onFileStaged?: (file: File) => void;
  onFileCleared?: () => void;
  onAnalyze?: (file?: File) => void;

  // Controlled staged file support
  stagedFile?: File | null;

  // Backward compatibility
  onFileAccepted?: (
    file: File,
    metadata: { detectedKind: DetectedFileKind; detectedFormat: DetectedFormat }
  ) => void;
  onError?: (errorMessage: string) => void;
  disabled?: boolean;
  isAnalyzing?: boolean;
  className?: string;
}

export function MultiFormatDropzone({
  onFileStaged,
  onFileCleared,
  onAnalyze,
  stagedFile: controlledStagedFile,
  onFileAccepted,
  onError,
  disabled = false,
  isAnalyzing = false,
  className = "",
}: MultiFormatDropzoneProps) {
  const [internalStagedFile, setInternalStagedFile] = useState<File | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragCounterRef = useRef(0);

  // Resolved staged file (controlled or internal state)
  const currentStagedFile =
    controlledStagedFile !== undefined ? controlledStagedFile : internalStagedFile;

  const validateAndProcessFile = useCallback(
    (file: File) => {
      setErrorMessage(null);

      // 1. Enforce 25MB hard size limit client-side
      if (file.size > MAX_FILE_SIZE_BYTES) {
        const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
        const err = `File exceeds the 25MB limit (${sizeMb} MB). Foresight processes files up to 25MB.`;
        setErrorMessage(err);
        onError?.(err);
        return;
      }

      // 2. Format & extension validation
      const ext = file.name.split(".").pop()?.toLowerCase() || "";
      const meta = ACCEPTED_EXTENSIONS_MAP[ext];
      if (!meta) {
        const displayExt = ext ? `.${ext}` : "without an extension";
        const err = `Unsupported file format (${displayExt}). Accepted formats: CSV, TSV, XLSX, XLS, Parquet, PDF, DOCX, TXT, MD.`;
        setErrorMessage(err);
        onError?.(err);
        return;
      }

      // Valid file: stage it
      setInternalStagedFile(file);
      onFileStaged?.(file);
      onFileAccepted?.(file, meta);
    },
    [onError, onFileAccepted, onFileStaged]
  );

  const handleDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;
    dragCounterRef.current += 1;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragActive(true);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;
    if (!isDragActive) {
      setIsDragActive(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;
    dragCounterRef.current -= 1;
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0;
      setIsDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current = 0;
    setIsDragActive(false);
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
      // Reset input value so same file can be selected again if desired
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

  const handleClear = () => {
    setInternalStagedFile(null);
    setErrorMessage(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    onFileCleared?.();
  };

  const handleAnalyze = () => {
    onAnalyze?.(currentStagedFile || undefined);
  };

  // State 2: Staged
  if (currentStagedFile) {
    return (
      <div className={`w-full space-y-3 ${className}`}>
        <StagedFileCard
          fileName={currentStagedFile.name}
          fileSizeLabel={formatFileSize(currentStagedFile.size)}
          formatBadge={getFormatBadge(currentStagedFile.name)}
          onClear={handleClear}
          onAnalyze={handleAnalyze}
          isAnalyzing={isAnalyzing}
        />

        {errorMessage && (
          <div
            role="alert"
            className="flex items-center gap-2.5 p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm animate-in fade-in duration-150"
          >
            <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-500" />
            <p className="font-medium text-xs md:text-sm">{errorMessage}</p>
          </div>
        )}
      </div>
    );
  }

  // State 1: Empty
  return (
    <div className={`w-full space-y-3 ${className}`}>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        onClick={handleBrowseClick}
        onKeyDown={handleKeyDown}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        aria-label="Upload file: Drag and drop your file here, or browse"
        className={`relative w-full rounded-2xl p-8 md:p-12 text-center cursor-pointer transition-all duration-200 select-none bg-white border-2 border-dashed ${
          isDragActive
            ? "border-blue-600 bg-blue-50/50 scale-[1.005]"
            : "border-slate-300 hover:border-slate-400 hover:bg-slate-50/60"
        } ${disabled ? "opacity-50 cursor-not-allowed pointer-events-none" : ""} focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2`}
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
          {/* Upload icon */}
          <div
            className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-colors duration-200 ${
              isDragActive
                ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                : "bg-slate-100 text-slate-500"
            }`}
          >
            <UploadCloud className="w-7 h-7" aria-hidden="true" />
          </div>

          {/* Prompt text */}
          <div className="space-y-1 max-w-md">
            <p className="text-base md:text-lg font-semibold text-slate-900">
              Drag and drop your file here, or{" "}
              <span className="text-blue-600 underline underline-offset-2">browse</span>
            </p>
            <p className="text-xs md:text-sm text-slate-500">
              Max file size 25MB • Up to 1 file per analysis
            </p>
          </div>

          {/* File-type tag badges: CSV/XLSX/PDF/DOCX/TXT */}
          <div className="flex flex-wrap items-center justify-center gap-2 pt-1">
            {["CSV", "XLSX", "PDF", "DOCX", "TXT"].map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Inline error message */}
      {errorMessage && (
        <div
          role="alert"
          className="flex items-center gap-2.5 p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm animate-in fade-in duration-150"
        >
          <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-500" />
          <p className="font-medium text-xs md:text-sm">{errorMessage}</p>
        </div>
      )}
    </div>
  );
}
