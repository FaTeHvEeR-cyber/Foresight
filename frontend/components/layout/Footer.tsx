"use client";

import React from "react";
import { Terminal, Shield, Cpu } from "lucide-react";

export function Footer() {
  return (
    <footer className="w-full border-t border-slate-800/80 bg-[#0a0d14] mt-20 py-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="space-y-1 text-center md:text-left">
            <div className="flex items-center justify-center md:justify-start gap-2">
              <span className="font-semibold text-sm text-slate-200">Foresight</span>
              <span className="text-xs text-slate-500">— Multimodal Decision Intelligence</span>
            </div>
            <p className="text-xs text-slate-500 max-w-lg">
              Rule-based tab orchestration for predictive time-series (Engine A), statistical hypothesis testing,
              unsupervised segmentation (Engine B), and local document summarization (Engine C).
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-4 text-xs text-slate-400">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-900 border border-slate-800">
              <Cpu className="w-3.5 h-3.5 text-blue-400" />
              <span>FastAPI Backend</span>
            </div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-900 border border-slate-800">
              <Terminal className="w-3.5 h-3.5 text-emerald-400" />
              <span>Next.js App Router</span>
            </div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-900 border border-slate-800">
              <Shield className="w-3.5 h-3.5 text-cyan-400" />
              <span>100% In-Memory Local</span>
            </div>
          </div>
        </div>

        <div className="mt-8 pt-6 border-t border-slate-900 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-600">
          <p>© {new Date().getFullYear()} Foresight. Local execution • No cloud egress.</p>
          <div className="flex items-center gap-4">
            <span>25MB Guardrail Active</span>
            <span>•</span>
            <span>REST Data Contracts Compliant</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
