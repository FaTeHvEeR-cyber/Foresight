"use client";

import React, { useState } from "react";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { TrustStrip } from "@/components/layout/TrustStrip";
import { FeatureCards } from "@/components/layout/FeatureCards";
import { MultiFormatDropzone } from "@/components/dropzone/MultiFormatDropzone";
import { QueryBar } from "@/components/query/QueryBar";
import { ModeChips } from "@/components/query/ModeChips";
import type { RepresentationModePreference } from "@/types/schema";
import { FileSpreadsheet, FileText } from "lucide-react";

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<RepresentationModePreference>("auto");
  const [stagedFile, setStagedFile] = useState<File | null>(null);

  const handleAnalyze = (file?: File) => {
    const activeFile = file || stagedFile;
    console.log("Analyze requested:", {
      fileName: activeFile ? activeFile.name : null,
      query,
      mode,
    });
  };

  const handleSampleClick = (sampleName: string) => {
    console.log(`Sample selected: ${sampleName}`);
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-slate-900 flex flex-col justify-between selection:bg-blue-600 selection:text-white">
      <Header />

      <main className="flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12 sm:py-16 space-y-12">
        {/* Hero Section */}
        <section className="text-center space-y-3">
          <h1 className="text-3xl sm:text-4xl md:text-5xl font-extrabold text-slate-900 tracking-tight">
            Upload your data. Get instant analysis.
          </h1>
          <p className="text-base sm:text-lg text-slate-600 max-w-2xl mx-auto leading-relaxed">
            No sign-up required. Your data is analyzed entirely in-memory and never stored.
          </p>
        </section>

        {/* Dropzone & Query Composition */}
        <section className="space-y-6">
          <MultiFormatDropzone
            stagedFile={stagedFile}
            onFileStaged={setStagedFile}
            onFileCleared={() => setStagedFile(null)}
            onAnalyze={handleAnalyze}
          />

          <div className="space-y-4">
            <QueryBar
              value={query}
              onChange={setQuery}
              placeholder="Ask a question or focus analysis — optional (e.g., 'Find outliers in margin vs cost')"
            />

            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-1">
              <span className="text-xs font-medium text-slate-500">
                Preferred analysis representation:
              </span>
              <ModeChips value={mode} onChange={setMode} />
            </div>
          </div>

          {/* Try with sample row */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
            <span className="text-xs sm:text-sm font-medium text-slate-500">
              Try with sample:
            </span>
            <div className="flex flex-wrap items-center justify-center gap-2.5">
              <button
                type="button"
                onClick={() => handleSampleClick("Retail Sales .xlsx")}
                className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-slate-200 bg-white text-xs sm:text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 hover:border-slate-300 hover:text-slate-900 transition-all duration-150 active:scale-[0.98]"
              >
                <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
                <span>Retail Sales .xlsx</span>
              </button>
              <button
                type="button"
                onClick={() => handleSampleClick("Research Dossier .pdf")}
                className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-slate-200 bg-white text-xs sm:text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 hover:border-slate-300 hover:text-slate-900 transition-all duration-150 active:scale-[0.98]"
              >
                <FileText className="w-4 h-4 text-rose-600" />
                <span>Research Dossier .pdf</span>
              </button>
            </div>
          </div>
        </section>

        {/* Enterprise Trust Strip */}
        <section className="rounded-2xl overflow-hidden border border-slate-800/60 shadow-sm">
          <TrustStrip />
        </section>

        {/* Capabilities Grid */}
        <section>
          <FeatureCards />
        </section>
      </main>

      <Footer />
    </div>
  );
}
