import React from "react";
import { TrendingUp } from "lucide-react";

export function Header() {
  return (
    <header className="w-full border-b border-slate-800 bg-[#0a0d14]/80 backdrop-blur-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Left: Logo mark + Wordmark */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white">
            <TrendingUp className="w-4 h-4" />
          </div>
          <span className="text-lg font-semibold text-white tracking-tight">
            Foresight
          </span>
        </div>

        {/* Right: About link */}
        <nav>
          <a
            href="#about"
            className="text-sm font-medium text-slate-400 hover:text-white transition-colors"
          >
            About
          </a>
        </nav>
      </div>
    </header>
  );
}

export default Header;
