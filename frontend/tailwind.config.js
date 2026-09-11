/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0a0d14",
        foreground: "#f3f4f6",
        surface: {
          50: "#161b26",
          100: "#1c2230",
          200: "#242c3d",
          300: "#2f384c",
        },
        brand: {
          primary: "#3b82f6",
          hover: "#2563eb",
          accent: "#06b6d4",
          violet: "#8b5cf6",
        },
      },
    },
  },
  plugins: [],
};
