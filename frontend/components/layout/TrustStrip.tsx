import React from "react";
import { ShieldCheck, Cpu, HardDrive } from "lucide-react";

const trustItems = [
  { label: "No account required", icon: ShieldCheck },
  { label: "In-memory processing", icon: Cpu },
  { label: "Max 25MB file size", icon: HardDrive },
];

export function TrustStrip() {
  return (
    <div className="w-full py-4 border-y border-slate-800/80 bg-slate-950/30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center justify-center gap-8 sm:gap-12 text-xs sm:text-sm text-slate-400">
          {trustItems.map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.label} className="flex items-center gap-2">
                <Icon className="w-4 h-4 text-slate-400" />
                <span>{item.label}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default TrustStrip;
