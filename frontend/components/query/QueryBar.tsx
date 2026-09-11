"use client";

/**
 * ============================================================================
 * COSMETIC-ONLY COMPONENT
 * ============================================================================
 * Note: Per parked routing architecture decisions, backend natural-language /
 * GLM routing is currently not active. This QueryBar component is COSMETIC-ONLY.
 * It provides the visual and interactive UI surface for exploratory prompts,
 * allowing users to type and submit inquiries locally without making backend calls.
 * ============================================================================
 */

import React, { useState } from "react";
import { Search, Sparkles, CornerDownLeft } from "lucide-react";

export interface QueryBarProps {
  placeholder?: string;
  onQuerySubmit?: (query: string) => void;
  disabled?: boolean;
}

export function QueryBar({
  placeholder = "Ask Foresight about trends, anomalies, or projections (e.g. 'Project Q4 churn with Welch test')...",
  onQuerySubmit,
  disabled = false,
}: QueryBarProps) {
  const [query, setQuery] = useState("");
  const [submittedFeedback, setSubmittedFeedback] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || disabled) return;

    // COSMETIC-ONLY: Inform user that routing is parked while logging the local prompt
    setSubmittedFeedback(`Query received (Cosmetic Mode): "${query.trim()}"`);
    onQuerySubmit?.(query.trim());

    // Auto-clear feedback after 4 seconds
    setTimeout(() => {
      setSubmittedFeedback(null);
    }, 4000);
  };

  return (
    <div className="w-full space-y-2">
      {/* COSMETIC-ONLY Comment Header Marker (Rendered as subtle badge) */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-1.5 text-xs text-slate-400 font-medium">
          <Sparkles className="w-3.5 h-3.5 text-blue-400" />
          <span>Natural Language Exploration</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
            UI Preview (Cosmetic)
          </span>
        </div>
        <span className="text-[11px] text-slate-500 hidden sm:inline">
          LLM routing parked • Rule-based tab resolution active
        </span>
      </div>

      <form onSubmit={handleSubmit} className="relative w-full">
        <div className="relative flex items-center">
          <div className="absolute left-4 pointer-events-none text-slate-500">
            <Search className="w-5 h-5" />
          </div>

          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={disabled}
            placeholder={placeholder}
            className="w-full pl-12 pr-28 py-3.5 rounded-xl bg-slate-900/80 border border-slate-700/80 text-sm text-gray-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all duration-200 shadow-inner disabled:opacity-50"
          />

          <div className="absolute right-2 flex items-center gap-1.5">
            <button
              type="submit"
              disabled={disabled || !query.trim()}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              title="Submit query (Cosmetic)"
            >
              <span>Explore</span>
              <CornerDownLeft className="w-3 h-3" />
            </button>
          </div>
        </div>
      </form>

      {/* Cosmetic submission indicator */}
      {submittedFeedback && (
        <div className="text-xs text-blue-400/90 px-2 py-1 rounded bg-blue-950/40 border border-blue-900/50 flex items-center justify-between animate-in fade-in">
          <span>{submittedFeedback}</span>
          <span className="text-[10px] text-slate-400 italic">Cosmetic interface</span>
        </div>
      )}
    </div>
  );
}
