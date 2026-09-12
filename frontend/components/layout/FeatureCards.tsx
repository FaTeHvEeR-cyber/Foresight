import React from "react";
import { LayoutDashboard, FileText, TrendingUp } from "lucide-react";

const features = [
  {
    title: "Dynamic Dashboards",
    description: "Interactive visual analytics and responsive metric tracking tailored to your uploaded data.",
    icon: LayoutDashboard,
  },
  {
    title: "Executive Reports",
    description: "Concise document summaries and structured briefing takeaways generated completely in-memory.",
    icon: FileText,
  },
  {
    title: "Outlier & Trend Flags",
    description: "Automated anomaly detection and statistical trend modeling to highlight critical shifts.",
    icon: TrendingUp,
  },
];

export function FeatureCards() {
  return (
    <div className="w-full">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {features.map((feature) => {
          const Icon = feature.icon;
          return (
            <div
              key={feature.title}
              className="bg-white border border-slate-200 rounded-xl p-6 transition-colors"
            >
              <div className="w-9 h-9 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center mb-4">
                <Icon className="w-5 h-5" />
              </div>
              <h3 className="text-base font-semibold text-slate-900 mb-1">
                {feature.title}
              </h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                {feature.description}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default FeatureCards;
