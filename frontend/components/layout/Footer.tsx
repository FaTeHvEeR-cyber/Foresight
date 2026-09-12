import React from "react";

export function Footer() {
  return (
    <footer className="w-full border-t border-slate-800 py-6 text-sm text-slate-400">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
        {/* Privacy note & License links */}
        <div className="flex items-center gap-6">
          <a
            href="#privacy"
            className="hover:text-slate-200 transition-colors"
          >
            Files are never stored
          </a>
          <a
            href="#license"
            className="hover:text-slate-200 transition-colors"
          >
            License
          </a>
        </div>

        {/* Version tag */}
        <div>
          <span className="text-xs font-mono text-slate-400">v0.1.0</span>
        </div>
      </div>
    </footer>
  );
}

export default Footer;
