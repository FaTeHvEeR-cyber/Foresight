"use client";

import React, { useState } from "react";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { TrustStrip } from "@/components/layout/TrustStrip";
import { FeatureCards } from "@/components/layout/FeatureCards";
import { MultiFormatDropzone } from "@/components/dropzone/MultiFormatDropzone";
import { QueryBar } from "@/components/query/QueryBar";
import { ModeChips } from "@/components/query/ModeChips";

import type {
  DetectedFileKind,
  DetectedFormat,
  UploadResponse,
  ForecastResponse,
  HypothesisResponse,
  SegmentationResponse,
  DocumentSummaryResponse,
} from "@/types/api";
import {
  resolveTabsForUpload,
  type DashboardTab,
  type TabId,
  type RepresentationModePreference,
} from "@/types/schema";

import {
  TrendingUp,
  BarChart3,
  GitFork,
  FileText,
  Layers,
  CheckCircle2,
  Table as TableIcon,
  Sparkles,
  ArrowRight,
  Database,
  Calendar,
} from "lucide-react";

export default function HomePage() {
  // Local state for staged file and detection
  const [stagedFile, setStagedFile] = useState<File | null>(null);
  const [detectedKind, setDetectedKind] = useState<DetectedFileKind>("tabular");
  const [detectedFormat, setDetectedFormat] = useState<DetectedFormat>("csv");

  // Local state for cosmetic query & representation mode
  const [modePreference, setModePreference] = useState<RepresentationModePreference>("auto");
  const [queryText, setQueryText] = useState("");

  // Analysis & Processing State
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isAnalyzed, setIsAnalyzed] = useState(false);
  const [uploadMetadata, setUploadMetadata] = useState<UploadResponse | null>(null);
  const [forecastData, setForecastData] = useState<ForecastResponse | null>(null);
  const [hypothesisData, setHypothesisData] = useState<HypothesisResponse | null>(null);
  const [segmentationData, setSegmentationData] = useState<SegmentationResponse | null>(null);
  const [documentSummaryData, setDocumentSummaryData] = useState<DocumentSummaryResponse | null>(null);

  // Dynamic Tabs state
  const [activeTabId, setActiveTabId] = useState<TabId>("overview");

  // Dynamically resolve tabs based on detectedKind (rule-based switch statement)
  const resolvedTabs: DashboardTab[] = resolveTabsForUpload(detectedKind);

  // Handlers
  const handleFileAccepted = (
    file: File,
    meta: { detectedKind: DetectedFileKind; detectedFormat: DetectedFormat }
  ) => {
    setStagedFile(file);
    setDetectedKind(meta.detectedKind);
    setDetectedFormat(meta.detectedFormat);
    setIsAnalyzed(false);
    setActiveTabId("overview");
  };

  const handleRemoveFile = () => {
    setStagedFile(null);
    setIsAnalyzed(false);
    setIsAnalyzing(false);
    setUploadMetadata(null);
    setForecastData(null);
    setHypothesisData(null);
    setSegmentationData(null);
    setDocumentSummaryData(null);
    setActiveTabId("overview");
  };

  // Simulate local analysis run matching API data contracts
  const handleAnalyze = () => {
    if (!stagedFile) return;
    setIsAnalyzing(true);

    setTimeout(() => {
      setIsAnalyzing(false);
      setIsAnalyzed(true);

      if (detectedKind === "tabular") {
        // Mock tabular upload metadata
        setUploadMetadata({
          fileId: `file_${Math.random().toString(36).substring(2, 9)}`,
          fileName: stagedFile.name,
          fileSizeBytes: stagedFile.size,
          detectedKind: "tabular",
          detectedFormat: detectedFormat,
          rowCount: 1420,
          columnCount: 6,
          memoryUsageBytes: stagedFile.size,
          columns: [
            { name: "timestamp", inferredType: "datetime", nullCount: 0 },
            { name: "revenue_usd", inferredType: "numeric", nullCount: 0 },
            { name: "units_sold", inferredType: "numeric", nullCount: 4 },
            { name: "channel", inferredType: "categorical", nullCount: 0 },
            { name: "discount_applied", inferredType: "boolean", nullCount: 0 },
            { name: "customer_segment", inferredType: "categorical", nullCount: 2 },
          ],
        });

        // Mock Engine A Forecast
        setForecastData({
          dates: ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06", "2026-09-07"],
          actuals: [1200, 1340, 1290, 1450, 1580, 1620, 1710],
          forecasts: [1210, 1335, 1300, 1440, 1590, 1640, 1730],
          metrics: {
            rmspe: 0.0184,
            mae: 14.8,
            rmse: 18.2,
            r2: 0.984,
          },
          modelUsed: "xgboost",
        });

        // Mock Engine A Hypothesis Test
        setHypothesisData({
          testType: "welch_t_test",
          pValue: 0.0034,
          isSignificant: true,
          alpha: 0.05,
          groups: ["Direct Channel", "Organic Search"],
        });

        // Mock Engine B Segmentation
        setSegmentationData({
          points: [
            { x: 1.2, y: 2.4, clusterId: 0 },
            { x: 1.5, y: 2.1, clusterId: 0 },
            { x: 1.1, y: 2.8, clusterId: 0 },
            { x: 5.4, y: 6.2, clusterId: 1 },
            { x: 5.8, y: 5.9, clusterId: 1 },
            { x: 8.9, y: 1.2, clusterId: 2 },
            { x: 9.1, y: 1.5, clusterId: 2 },
            { x: 4.0, y: 9.5, clusterId: -1 }, // Outlier
          ],
          clusterCount: 3,
          outlierMask: [false, false, false, false, false, false, false, true],
          outlierScoreMethod: "isolation_forest",
        });
      } else {
        // Mock Document upload metadata
        setUploadMetadata({
          fileId: `doc_${Math.random().toString(36).substring(2, 9)}`,
          fileName: stagedFile.name,
          fileSizeBytes: stagedFile.size,
          detectedKind: "document",
          detectedFormat: detectedFormat,
          memoryUsageBytes: stagedFile.size,
        });

        // Mock Engine C Document Summary
        setDocumentSummaryData({
          summary:
            "This document presents the multi-quarter performance assessment and strategic operational review. Core revenue drivers expanded by 24% year-over-year, driven by enterprise cloud adoption and reduced infrastructure overhead. Risk vectors remain confined to supplier lead times.",
          keyTakeaways: [
            "Gross margins improved by 340 bps following local orchestration optimizations.",
            "Zero cloud data egress verified across all customer data pipelines.",
            "Identified potential supply chain bottleneck in hardware procurement cycle for Q4.",
            "Recommended automated outlier masking before compiling consolidated quarterly rollups.",
          ],
          detectedDocType: "report",
          extractedTables: [
            {
              caption: "Financial Trajectory Summary",
              rows: [
                ["Metric", "Q1 Actual", "Q2 Actual", "Q3 Projected"],
                ["Gross Revenue ($M)", "42.5", "48.2", "55.8"],
                ["Operating Margin", "22.4%", "24.1%", "26.3%"],
                ["Inference Latency", "34ms", "28ms", "21ms"],
              ],
            },
          ],
        });
      }
    }, 1200);
  };

  // Quick sample loaders for testing
  const loadSampleFile = (kind: "tabular" | "document") => {
    if (kind === "tabular") {
      const sampleBlob = new File(
        ["timestamp,revenue,units\n2026-09-01,1200,45\n2026-09-02,1340,52"],
        "quarterly_sales_forecast.csv",
        { type: "text/csv" }
      );
      handleFileAccepted(sampleBlob, { detectedKind: "tabular", detectedFormat: "csv" });
    } else {
      const sampleBlob = new File(
        ["# Executive Brief\nPerformance analysis and key risk assessment."],
        "strategic_overview.pdf",
        { type: "application/pdf" }
      );
      handleFileAccepted(sampleBlob, { detectedKind: "document", detectedFormat: "pdf" });
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#0a0d14] text-slate-100">
      <Header />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-10">
        {/* Hero Section */}
        <section className="text-center space-y-4 pt-4 max-w-3xl mx-auto">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-950/60 border border-blue-800/40 text-xs font-semibold text-blue-400">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Rule-Based Multimodal Orchestration</span>
          </div>
          <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-white">
            Unified Analytics & Forecast Engine
          </h1>
          <p className="text-sm sm:text-base text-slate-400 leading-relaxed">
            Drop time-series or tabular data for sub-second XGBoost/MLP forecasts and statistical tests,
            or documents for local, zero-leakage NLP summarization.
          </p>
        </section>

        {/* Cosmetic Exploratory Layer: QueryBar & ModeChips */}
        <section className="max-w-4xl mx-auto space-y-3.5">
          <QueryBar
            value={queryText}
            onChange={setQueryText}
          />
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <ModeChips value={modePreference} onChange={setModePreference} />

            {/* Quick Demo Preloads */}
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-500">Quick Test:</span>
              <button
                type="button"
                onClick={() => loadSampleFile("tabular")}
                className="px-2.5 py-1 rounded bg-slate-900 hover:bg-slate-800 border border-slate-700 text-blue-400 hover:text-blue-300 transition-colors"
              >
                + Sample CSV
              </button>
              <button
                type="button"
                onClick={() => loadSampleFile("document")}
                className="px-2.5 py-1 rounded bg-slate-900 hover:bg-slate-800 border border-slate-700 text-cyan-400 hover:text-cyan-300 transition-colors"
              >
                + Sample PDF
              </button>
            </div>
          </div>
        </section>

        {/* Ingestion & Dropzone Area */}
        <section className="max-w-4xl mx-auto space-y-4">
          <MultiFormatDropzone
            stagedFile={stagedFile}
            onFileStaged={(file) => {
              const ext = file.name.split(".").pop()?.toLowerCase() || "";
              const kind = ["csv", "tsv", "xlsx", "xls", "parquet"].includes(ext)
                ? "tabular"
                : "document";
              handleFileAccepted(file, {
                detectedKind: kind,
                detectedFormat: ext as DetectedFormat,
              });
            }}
            onFileCleared={handleRemoveFile}
            onAnalyze={handleAnalyze}
            isAnalyzing={isAnalyzing}
          />
        </section>

        {/* Dynamic Tabs & Results Preview Area */}
        {stagedFile && isAnalyzed && (
          <section className="max-w-5xl mx-auto space-y-6 animate-in fade-in slide-in-from-bottom-3 duration-300">
            {/* Tab Navigation Header (Dynamically Resolved) */}
            <div className="border-b border-slate-800 flex items-center gap-2 overflow-x-auto pb-px">
              {resolvedTabs.map((tab) => {
                const isActive = activeTabId === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTabId(tab.id)}
                    className={`inline-flex items-center gap-2 px-4 py-2.5 text-xs sm:text-sm font-semibold border-b-2 transition-all duration-150 whitespace-nowrap ${
                      isActive
                        ? "border-blue-500 text-blue-400 bg-blue-950/20"
                        : "border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700"
                    }`}
                  >
                    <span>{tab.label}</span>
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800/80 text-slate-400 font-mono">
                      {tab.sourceEngine}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Tab Content Panels */}
            <div className="rounded-2xl glass-panel p-6 border border-slate-800 shadow-xl min-h-[320px]">
              {/* Overview Tab */}
              {activeTabId === "overview" && uploadMetadata && (
                <div className="space-y-6">
                  <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-800">
                    <div>
                      <h3 className="text-lg font-bold text-white">Dataset & File Ingestion Overview</h3>
                      <p className="text-xs text-slate-400">
                        In-memory schema detection and hardware telemetry.
                      </p>
                    </div>
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-950/60 border border-emerald-800/40 text-xs text-emerald-400 font-medium">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Schema Validated</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                      <span className="text-[11px] text-slate-400 uppercase font-semibold tracking-wider">
                        File Kind
                      </span>
                      <p className="text-lg font-bold text-white capitalize mt-1">
                        {uploadMetadata.detectedKind}
                      </p>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                      <span className="text-[11px] text-slate-400 uppercase font-semibold tracking-wider">
                        Format
                      </span>
                      <p className="text-lg font-bold text-blue-400 uppercase mt-1">
                        .{uploadMetadata.detectedFormat}
                      </p>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                      <span className="text-[11px] text-slate-400 uppercase font-semibold tracking-wider">
                        {uploadMetadata.rowCount ? "Row Count" : "File Size"}
                      </span>
                      <p className="text-lg font-bold text-white mt-1">
                        {uploadMetadata.rowCount
                          ? uploadMetadata.rowCount.toLocaleString()
                          : `${(uploadMetadata.fileSizeBytes / 1024).toFixed(1)} KB`}
                      </p>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                      <span className="text-[11px] text-slate-400 uppercase font-semibold tracking-wider">
                        Memory Buffer
                      </span>
                      <p className="text-lg font-bold text-amber-400 mt-1">
                        {(uploadMetadata.memoryUsageBytes / 1024).toFixed(1)} KB
                      </p>
                    </div>
                  </div>

                  {uploadMetadata.columns && uploadMetadata.columns.length > 0 && (
                    <div className="space-y-3 pt-2">
                      <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                        Inferred Column Schema ({uploadMetadata.columns.length} columns)
                      </h4>
                      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                        {uploadMetadata.columns.map((col, cIdx) => (
                          <div
                            key={cIdx}
                            className="p-3 rounded-lg bg-slate-900/60 border border-slate-800/80 flex items-center justify-between"
                          >
                            <span className="text-xs font-medium text-slate-200 font-mono truncate">
                              {col.name}
                            </span>
                            <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-blue-300 border border-slate-700">
                              {col.inferredType}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Forecasts Tab (Engine A) */}
              {activeTabId === "forecast" && forecastData && (
                <div className="space-y-6">
                  <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-800">
                    <div>
                      <h3 className="text-lg font-bold text-white">
                        Engine A — Predictive Time-Series Forecasting
                      </h3>
                      <p className="text-xs text-slate-400">
                        Evaluated via {forecastData.modelUsed.toUpperCase()} regressor with RMSPE optimization.
                      </p>
                    </div>
                    <div className="text-xs px-3 py-1 rounded bg-blue-950/60 border border-blue-800/50 text-blue-300 font-medium">
                      Model: {forecastData.modelUsed.toUpperCase()}
                    </div>
                  </div>

                  {/* Metrics Row */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                      <span className="text-[11px] text-slate-400 uppercase font-semibold">RMSPE</span>
                      <p className="text-xl font-bold text-emerald-400 mt-1">
                        {(forecastData.metrics.rmspe * 100).toFixed(2)}%
                      </p>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                      <span className="text-[11px] text-slate-400 uppercase font-semibold">R² Score</span>
                      <p className="text-xl font-bold text-blue-400 mt-1">
                        {forecastData.metrics.r2.toFixed(3)}
                      </p>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                      <span className="text-[11px] text-slate-400 uppercase font-semibold">MAE</span>
                      <p className="text-xl font-bold text-white mt-1">
                        {forecastData.metrics.mae}
                      </p>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                      <span className="text-[11px] text-slate-400 uppercase font-semibold">RMSE</span>
                      <p className="text-xl font-bold text-white mt-1">
                        {forecastData.metrics.rmse}
                      </p>
                    </div>
                  </div>

                  {/* SVG Forecast Sparkline / Comparison Chart */}
                  <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-4">
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <div className="flex items-center gap-4">
                        <span className="flex items-center gap-1.5">
                          <span className="w-3 h-0.5 bg-blue-400"></span> Actual Values
                        </span>
                        <span className="flex items-center gap-1.5">
                          <span className="w-3 h-0.5 bg-emerald-400 border-dashed"></span> Forecast Values
                        </span>
                      </div>
                      <span className="font-mono">7-Day Trajectory</span>
                    </div>

                    <div className="h-40 w-full flex items-end justify-between gap-2 pt-6">
                      {forecastData.dates.map((date, idx) => {
                        const actual = forecastData.actuals[idx];
                        const forecast = forecastData.forecasts[idx];
                        const maxVal = 1800;
                        const actualHeight = `${(actual / maxVal) * 100}%`;
                        const forecastHeight = `${(forecast / maxVal) * 100}%`;

                        return (
                          <div key={idx} className="flex-1 flex flex-col items-center gap-1.5 h-full justify-end">
                            <div className="w-full flex items-end justify-center gap-1 h-full">
                              <div
                                style={{ height: actualHeight }}
                                className="w-3 sm:w-5 bg-blue-500/70 hover:bg-blue-400 rounded-t transition-all"
                                title={`Actual: ${actual}`}
                              />
                              <div
                                style={{ height: forecastHeight }}
                                className="w-3 sm:w-5 bg-emerald-500/70 hover:bg-emerald-400 rounded-t transition-all"
                                title={`Forecast: ${forecast}`}
                              />
                            </div>
                            <span className="text-[10px] text-slate-500 font-mono truncate max-w-[50px]">
                              {date.split("-").slice(1).join("/")}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* Stats Tab (Engine A Hypothesis Testing) */}
              {activeTabId === "stats" && hypothesisData && (
                <div className="space-y-6">
                  <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-800">
                    <div>
                      <h3 className="text-lg font-bold text-white">
                        Engine A — Hypothesis & Statistical Testing
                      </h3>
                      <p className="text-xs text-slate-400">
                        Sub-second Welch’s t-test and ANOVA for subgroup variances.
                      </p>
                    </div>
                    <span
                      className={`text-xs px-3 py-1 rounded-full font-semibold border ${
                        hypothesisData.isSignificant
                          ? "bg-emerald-950/60 text-emerald-400 border-emerald-800/60"
                          : "bg-slate-800 text-slate-300 border-slate-700"
                      }`}
                    >
                      {hypothesisData.isSignificant ? "Statistically Significant" : "Not Significant"}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                      <span className="text-[11px] text-slate-400 uppercase font-semibold">Test Method</span>
                      <p className="text-base font-bold text-white capitalize mt-1">
                        {hypothesisData.testType.replace(/_/g, " ")}
                      </p>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                      <span className="text-[11px] text-slate-400 uppercase font-semibold">p-Value</span>
                      <p className="text-2xl font-extrabold text-blue-400 mt-1">
                        {hypothesisData.pValue.toFixed(4)}
                      </p>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                      <span className="text-[11px] text-slate-400 uppercase font-semibold">Alpha Boundary</span>
                      <p className="text-xl font-bold text-slate-200 mt-1">α = {hypothesisData.alpha}</p>
                    </div>
                  </div>

                  <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2">
                    <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                      Tested Contrast Groups
                    </span>
                    <div className="flex flex-wrap gap-2 pt-1">
                      {hypothesisData.groups.map((group, gIdx) => (
                        <span
                          key={gIdx}
                          className="px-3 py-1 rounded bg-slate-800/80 border border-slate-700 text-xs text-slate-300"
                        >
                          Group {gIdx + 1}: {group}
                        </span>
                      ))}
                    </div>
                    <p className="text-xs text-slate-400 pt-2">
                      p-value of {hypothesisData.pValue} is less than α={hypothesisData.alpha}, rejecting the null
                      hypothesis with high confidence.
                    </p>
                  </div>
                </div>
              )}

              {/* Segmentation Tab (Engine B) */}
              {activeTabId === "segmentation" && segmentationData && (
                <div className="space-y-6">
                  <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-800">
                    <div>
                      <h3 className="text-lg font-bold text-white">
                        Engine B — Unsupervised Segmentation & Anomaly Detection
                      </h3>
                      <p className="text-xs text-slate-400">
                        Isolation Forest outlier scoring & geometric cluster discovery.
                      </p>
                    </div>
                    <span className="text-xs px-3 py-1 rounded bg-purple-950/60 border border-purple-800/50 text-purple-300 font-medium">
                      Method: {segmentationData.outlierScoreMethod.replace(/_/g, " ")}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                      <span className="text-[11px] text-slate-400 uppercase font-semibold">Discovered Clusters</span>
                      <p className="text-2xl font-bold text-purple-400 mt-1">
                        {segmentationData.clusterCount} Cohorts
                      </p>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                      <span className="text-[11px] text-slate-400 uppercase font-semibold">Total Points</span>
                      <p className="text-2xl font-bold text-white mt-1">
                        {segmentationData.points.length}
                      </p>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                      <span className="text-[11px] text-slate-400 uppercase font-semibold">Masked Outliers</span>
                      <p className="text-2xl font-bold text-rose-400 mt-1">
                        {segmentationData.outlierMask.filter(Boolean).length} points
                      </p>
                    </div>
                  </div>

                  {/* 2D Projection Scatter Visualization */}
                  <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
                    <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                      2D Projection Scatter Map
                    </span>
                    <div className="h-44 w-full bg-slate-950/80 rounded-lg p-4 relative border border-slate-800/60 flex items-center justify-center">
                      <div className="relative w-full h-full">
                        {segmentationData.points.map((pt, pIdx) => {
                          const isOutlier = segmentationData.outlierMask[pIdx];
                          const leftPct = `${(pt.x / 10) * 85 + 5}%`;
                          const topPct = `${(pt.y / 10) * 80 + 10}%`;

                          return (
                            <div
                              key={pIdx}
                              style={{ left: leftPct, top: topPct }}
                              className={`absolute w-3.5 h-3.5 rounded-full -translate-x-1/2 -translate-y-1/2 transition-transform hover:scale-150 cursor-pointer ${
                                isOutlier
                                  ? "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.8)] animate-pulse"
                                  : pt.clusterId === 0
                                  ? "bg-blue-400"
                                  : pt.clusterId === 1
                                  ? "bg-emerald-400"
                                  : "bg-amber-400"
                              }`}
                              title={`Point (${pt.x}, ${pt.y}) - Cluster ${pt.clusterId}${
                                isOutlier ? " [Outlier]" : ""
                              }`}
                            />
                          );
                        })}
                      </div>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-slate-400 pt-1">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-blue-400"></span> Cluster 0
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span> Cluster 1
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-amber-400"></span> Cluster 2
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span> Outlier (Masked)
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Summary Tab (Engine C) */}
              {activeTabId === "summary" && documentSummaryData && (
                <div className="space-y-6">
                  <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-800">
                    <div>
                      <h3 className="text-lg font-bold text-white">
                        Engine C — Offline NLP Document Intelligence
                      </h3>
                      <p className="text-xs text-slate-400">
                        Local extractive summarization and key takeaway extraction.
                      </p>
                    </div>
                    <span className="text-xs px-3 py-1 rounded bg-cyan-950/60 border border-cyan-800/50 text-cyan-300 font-medium capitalize">
                      Type: {documentSummaryData.detectedDocType}
                    </span>
                  </div>

                  {/* Executive Summary */}
                  <div className="p-5 rounded-xl bg-slate-900/70 border border-slate-800 space-y-2">
                    <span className="text-xs font-semibold text-cyan-400 uppercase tracking-wider">
                      Executive Summary
                    </span>
                    <p className="text-sm text-slate-300 leading-relaxed">
                      {documentSummaryData.summary}
                    </p>
                  </div>

                  {/* Key Takeaways */}
                  <div className="space-y-3">
                    <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                      Synthesized Key Takeaways
                    </span>
                    <div className="grid grid-cols-1 gap-2.5">
                      {documentSummaryData.keyTakeaways.map((takeaway, tIdx) => (
                        <div
                          key={tIdx}
                          className="flex items-start gap-3 p-3.5 rounded-xl bg-slate-900/60 border border-slate-800/80"
                        >
                          <div className="w-5 h-5 rounded-full bg-cyan-950/80 border border-cyan-800/60 text-cyan-400 flex items-center justify-center text-xs flex-shrink-0 mt-0.5">
                            {tIdx + 1}
                          </div>
                          <span className="text-xs sm:text-sm text-slate-300 leading-normal">
                            {takeaway}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Extracted Tables */}
                  {documentSummaryData.extractedTables && documentSummaryData.extractedTables.length > 0 && (
                    <div className="space-y-3 pt-2">
                      <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                        Extracted Table Data
                      </span>
                      {documentSummaryData.extractedTables.map((table, tblIdx) => (
                        <div key={tblIdx} className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/50">
                          {table.caption && (
                            <div className="px-4 py-2 bg-slate-900 border-b border-slate-800 text-xs font-semibold text-slate-300">
                              {table.caption}
                            </div>
                          )}
                          <table className="w-full text-left text-xs text-slate-300">
                            <tbody>
                              {table.rows.map((row, rIdx) => (
                                <tr
                                  key={rIdx}
                                  className={`border-b border-slate-800/60 ${
                                    rIdx === 0 ? "bg-slate-800/60 font-semibold text-slate-200" : ""
                                  }`}
                                >
                                  {row.map((cell, cIdx) => (
                                    <td key={cIdx} className="px-4 py-2.5">
                                      {cell}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>
        )}

        {/* Capabilities Grid */}
        <FeatureCards />

        {/* Enterprise Trust Strip */}
        <TrustStrip />
      </main>

      <Footer />
    </div>
  );
}
