"use client";

import React from "react";
import { ShieldCheck, Zap, Lock, Database } from "lucide-react";

export function TrustStrip() {
  const trustItems = [
    {
      icon: Lock,
      title: "100% Local Processing",
      description: "Data stays strictly in-memory. Zero third-party telemetry or cloud egress.",
      color: "text-emerald-400",
    },
    {
      icon: Zap,
      title: "Sub-Second Statistics",
      description: "Instant Welch t-tests, ANOVA, and Ridge/XGBoost/MLP model evaluations.",
      color: "text-blue-400",
    },
    {
      icon: Database,
      title: "25MB Memory Guard",
      description: "Deterministic in-memory buffer guards against browser and host memory starvation.",
      color: "text-amber-400",
    },
    {
      icon: ShieldCheck,
      title: "Deterministic Routing",
      description: "Rule-based tab resolvers map detected types directly to specialized engines.",
      color: "text-cyan-400",
    },
  ];

  return (
    <section className="w-full py-6 border-y border-slate-800/60 bg-slate-950/40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {trustItems.map((item, idx) => {
            const Icon = item.icon;
            return (
              <div key={idx} className="flex items-start gap-3.5">
                <div className="p-2 rounded-xl bg-slate-900 border border-slate-800 flex-shrink-0">
                  <Icon className={`w-5 h-5 ${item.color}`} />
                </div>
                <div className="space-y-0.5">
                  <h4 className="text-xs font-semibold text-slate-200">{item.title}</h4>
                  <p className="text-[11px] text-slate-400 leading-relaxed">
                    {item.description}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
