"use client";

/**
 * COSMETIC-ONLY COMPONENT (Phase 1)
 *
 * no backend intent-classification or routing logic exists yet; any LLM-driven
 * schema routing is a parked, unevaluated future direction; these values are
 * captured in local state only and will just be passed as plain fields alongside
 * the upload once Phase 2 exists. Do not wire them to any API call.
 */

import React from "react";
import { Search } from "lucide-react";

export interface QueryBarProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  id?: string;
  name?: string;
}

export function QueryBar({
  value,
  onChange,
  placeholder = "Ask a question or focus analysis — optional (e.g., 'Find outliers in margin vs cost')",
  disabled = false,
  className = "",
  id,
  name,
}: QueryBarProps) {
  return (
    <div className={`relative w-full ${className}`}>
      <div className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400">
        <Search className="w-4 h-4 text-slate-400" aria-hidden="true" />
      </div>

      <input
        type="text"
        id={id}
        name={name}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-900/80 border border-slate-700/80 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
        aria-label="Analysis query input"
      />
    </div>
  );
}
