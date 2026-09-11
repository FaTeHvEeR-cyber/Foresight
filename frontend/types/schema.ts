import type { DetectedFileKind } from "./api";

export type TabId = "overview" | "forecast" | "stats" | "segmentation" | "summary";

export interface DashboardTab {
  id: TabId;
  label: string;
  sourceEngine: "engineA" | "engineB" | "engineC" | "meta";
}

/**
 * Rule-based tab set resolver mapping detected file kinds to dashboard tabs.
 * Plain switch statement — swappable and not tied to any LLM/routing logic.
 */
export function resolveTabsForUpload(detectedKind: DetectedFileKind): DashboardTab[] {
  switch (detectedKind) {
    case "tabular":
      return [
        { id: "overview", label: "Overview", sourceEngine: "meta" },
        { id: "forecast", label: "Forecasts", sourceEngine: "engineA" },
        { id: "stats", label: "Stats", sourceEngine: "engineA" },
        { id: "segmentation", label: "Segmentation", sourceEngine: "engineB" },
      ];
    case "document":
      return [
        { id: "overview", label: "Overview", sourceEngine: "meta" },
        { id: "summary", label: "Summary", sourceEngine: "engineC" },
      ];
    case "mixed":
      return [
        { id: "overview", label: "Overview", sourceEngine: "meta" },
        { id: "summary", label: "Summary", sourceEngine: "engineC" },
        { id: "stats", label: "Stats", sourceEngine: "engineA" },
        { id: "segmentation", label: "Segmentation", sourceEngine: "engineB" },
      ];
    default:
      return [{ id: "overview", label: "Overview", sourceEngine: "meta" }];
  }
}

/**
 * Client-side UI representation mode preference only.
 * Not wired to backend routing yet.
 */
export type RepresentationModePreference = "auto" | "dashboard" | "report";
