"use client";

import React from "react";
import { TrendingUp, GitFork, FileText, Cpu, Check } from "lucide-react";

export function FeatureCards() {
  const features = [
    {
      engine: "Engine A",
      title: "Forecasting & Statistics",
      badge: "Tabular",
      badgeColor: "bg-emerald-950/60 text-emerald-300 border-emerald-700/40",
      description:
        "High-precision time-series predictions powered by Ridge, XGBoost, and MLP regression alongside Welch's t-test and ANOVA hypothesis testing.",
      icon: TrendingUp,
      accent: "border-blue-500/20 hover:border-blue-500/50",
      iconBg: "bg-blue-950/50 text-blue-400 border-blue-800/40",
      capabilities: [
        "Ridge, XGBoost, & MLP model comparison",
        "RMSPE, MAE, RMSE & R² evaluation metrics",
        "Automated Welch t-test & ANOVA significance",
        "Fast columnar inference",
      ],
    },
    {
      engine: "Engine B",
      title: "Segmentation & Outliers",
      badge: "Clustering",
      badgeColor: "bg-purple-950/60 text-purple-300 border-purple-700/40",
      description:
        "Unsupervised geometric clustering and Isolation Forest anomaly detection to identify distinct cohorts and eliminate contaminated observations.",
      icon: GitFork,
      accent: "border-purple-500/20 hover:border-purple-500/50",
      iconBg: "bg-purple-950/50 text-purple-400 border-purple-800/40",
      capabilities: [
        "Isolation Forest outlier scoring & masking",
        "Adaptive cluster count determination",
        "2D projection point space mapping",
        "Sub-second cohort segmentation",
      ],
    },
    {
      engine: "Engine C",
      title: "Document Intelligence",
      badge: "NLP",
      badgeColor: "bg-cyan-950/60 text-cyan-300 border-cyan-700/40",
      description:
        "Local, offline NLP document comprehension extracting key executive takeaways, structural document classification, and embedded tables.",
      icon: FileText,
      accent: "border-cyan-500/20 hover:border-cyan-500/50",
      iconBg: "bg-cyan-950/50 text-cyan-400 border-cyan-800/40",
      capabilities: [
        "Contract, report & policy classification",
        "Bullet-point executive takeaway synthesis",
        "Structured table extraction from PDF/DOCX",
        "Zero cloud transmission — 100% offline",
      ],
    },
  ];

  return (
    <section className="w-full space-y-6">
      <div className="text-center max-w-2xl mx-auto space-y-2">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs font-medium text-slate-300">
          <Cpu className="w-3.5 h-3.5 text-blue-400" />
          <span>Multi-Engine Orchestration</span>
        </div>
        <h2 className="text-2xl font-bold text-white tracking-tight">
          Unified Analytics Pipeline
        </h2>
        <p className="text-sm text-slate-400">
          Foresight routes your data to specialized mathematical engines based on detected file types.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {features.map((feature, idx) => {
          const Icon = feature.icon;
          return (
            <div
              key={idx}
              className={`rounded-2xl glass-panel p-6 border transition-all duration-300 flex flex-col justify-between ${feature.accent}`}
            >
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className={`w-11 h-11 rounded-xl flex items-center justify-center border ${feature.iconBg}`}>
                    <Icon className="w-5 h-5" />
                  </div>
                  <span className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full border ${feature.badgeColor}`}>
                    {feature.engine} • {feature.badge}
                  </span>
                </div>

                <div className="space-y-1.5">
                  <h3 className="text-base font-semibold text-white">{feature.title}</h3>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    {feature.description}
                  </p>
                </div>

                <div className="pt-2 border-t border-slate-800/80 space-y-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                    Key Features
                  </span>
                  <ul className="space-y-1.5">
                    {feature.capabilities.map((cap, cIdx) => (
                      <li key={cIdx} className="flex items-center gap-2 text-xs text-slate-300">
                        <Check className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                        <span>{cap}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
