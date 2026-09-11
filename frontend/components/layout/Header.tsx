"use client";

import React from "react";
import { Activity, ShieldCheck, Compass, Sparkles } from "lucide-react";

export function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-800/80 bg-[#0a0d14]/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand Logo & Title */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-500 to-cyan-400 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Compass className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold text-white tracking-tight">Foresight</span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-blue-950 text-blue-400 border border-blue-800/60 uppercase tracking-wider">
                Phase 1
              </span>
            </div>
            <p className="text-xs text-slate-400 hidden sm:block">
              Multimodal Decision Intelligence
            </p>
          </div>
        </div>

        {/* Engine Status & Meta */}
        <div className="flex items-center gap-4">
          <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800 text-xs">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="text-slate-300 font-medium">Engines A/B/C:</span>
            <span className="text-emerald-400 font-semibold">Online & Local</span>
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span className="hidden lg:inline-flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-blue-400" />
              <span>25MB Guard Active</span>
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
