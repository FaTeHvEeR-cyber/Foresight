"use client";

/**
 * ============================================================================
 * COSMETIC-ONLY COMPONENT
 * ============================================================================
 * Note: RepresentationModePreference is a client-side UI preference switch.
 * Per the parked routing architecture, this component is COSMETIC-ONLY and is
 * NOT wired to backend routing. It toggles local display intent between Auto,
 * Dashboard, and Report modes without altering backend contracts.
 * ============================================================================
 */

import React from "react";
import { LayoutDashboard, FileText, Wand2 } from "lucide-react";
import type { RepresentationModePreference } from "@/types/schema";

export interface ModeChipsProps {
  selectedMode: RepresentationModePreference;
  onModeChange: (mode: RepresentationModePreference) => void;
  disabled?: boolean;
}

interface ModeOption {
  id: RepresentationModePreference;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
}

const MODES: ModeOption[] = [
  {
    id: "auto",
    label: "Auto Resolver",
    description: "Rule-based tab routing based on uploaded file type",
    icon: Wand2,
  },
  {
    id: "dashboard",
    label: "Dashboard Mode",
    description: "Visual charts, projections, and scatter clusters",
    icon: LayoutDashboard,
  },
  {
    id: "report",
    label: "Executive Report",
    description: "Narrative synthesis, key takeaways, and tables",
    icon: FileText,
  },
];

export function ModeChips({
  selectedMode,
  onModeChange,
  disabled = false,
}: ModeChipsProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-slate-500 font-medium mr-1 select-none">
        Representation Mode (Cosmetic):
      </span>

      {MODES.map((mode) => {
        const isSelected = selectedMode === mode.id;
        const Icon = mode.icon;

        return (
          <button
            key={mode.id}
            type="button"
            onClick={() => onModeChange(mode.id)}
            disabled={disabled}
            title={`${mode.label}: ${mode.description} (Cosmetic selector)`}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 border select-none ${
              isSelected
                ? "bg-blue-600/20 text-blue-300 border-blue-500/60 shadow-[0_0_12px_rgba(59,130,246,0.2)]"
                : "bg-slate-900/60 text-slate-400 border-slate-800 hover:border-slate-700 hover:text-slate-200"
            } ${disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`}
          >
            <Icon
              className={`w-3.5 h-3.5 ${
                isSelected ? "text-blue-400" : "text-slate-500"
              }`}
            />
            <span>{mode.label}</span>
          </button>
        );
      })}
    </div>
  );
}
