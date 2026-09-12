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
import type { RepresentationModePreference } from "@/types/schema";

export interface ModeChipsProps {
  value?: RepresentationModePreference;
  onChange?: (value: RepresentationModePreference) => void;
  // Backwards-compatibility props
  selectedMode?: RepresentationModePreference;
  onModeChange?: (mode: RepresentationModePreference) => void;
  disabled?: boolean;
  className?: string;
}

interface ModeOption {
  id: RepresentationModePreference;
  label: string;
}

const MODES: readonly ModeOption[] = [
  { id: "auto", label: "Auto-Detect (Default)" },
  { id: "dashboard", label: "Visual Dashboard" },
  { id: "report", label: "Executive Report" },
] as const;

export function ModeChips({
  value,
  onChange,
  selectedMode,
  onModeChange,
  disabled = false,
  className = "",
}: ModeChipsProps) {
  const activeMode = value ?? selectedMode ?? "auto";

  const handleSelect = (mode: RepresentationModePreference) => {
    if (disabled) return;
    onChange?.(mode);
    onModeChange?.(mode);
  };

  const handleKeyDown = (
    e: React.KeyboardEvent<HTMLButtonElement>,
    index: number
  ) => {
    if (disabled) return;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      const nextIndex = (index + 1) % MODES.length;
      handleSelect(MODES[nextIndex].id);
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      const prevIndex = (index - 1 + MODES.length) % MODES.length;
      handleSelect(MODES[prevIndex].id);
    }
  };

  return (
    <div
      role="radiogroup"
      aria-label="Representation Mode"
      className={`inline-flex items-center p-1 rounded-xl bg-slate-900/80 border border-slate-700/80 gap-1 ${className}`}
    >
      {MODES.map((mode, index) => {
        const isSelected = activeMode === mode.id;

        return (
          <button
            key={mode.id}
            type="button"
            role="radio"
            aria-checked={isSelected}
            tabIndex={isSelected ? 0 : -1}
            onClick={() => handleSelect(mode.id)}
            onKeyDown={(e) => handleKeyDown(e, index)}
            disabled={disabled}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 select-none focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40 disabled:opacity-50 disabled:cursor-not-allowed ${
              isSelected
                ? "bg-white text-slate-900 shadow font-semibold"
                : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white hover:bg-slate-800/40"
            }`}
          >
            {mode.label}
          </button>
        );
      })}
    </div>
  );
}
