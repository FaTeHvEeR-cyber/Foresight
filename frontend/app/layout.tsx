import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Foresight — Multimodal Decision Intelligence",
  description:
    "Unified predictive forecasting, statistical hypothesis testing, high-dimensional segmentation, and local document intelligence.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#0a0d14] text-gray-100 antialiased min-h-screen selection:bg-blue-600 selection:text-white">
        {children}
      </body>
    </html>
  );
}
