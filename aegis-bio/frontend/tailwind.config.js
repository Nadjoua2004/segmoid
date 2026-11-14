/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        space: {
          950: "#030712",
          900: "#0B0F19",
          850: "#111827",
          800: "#1F2937",
          700: "#374151",
        },
        hud: {
          cyan: "#00F0FF",
          blue: "#38BDF8",
          amber: "#F59E0B",
          red: "#EF4444",
          green: "#10B981",
          purple: "#A855F7",
        },
      },
      fontFamily: {
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
      animation: {
        "pulse-fast": "pulse 1.2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "glow-red": "glowRed 2s ease-in-out infinite alternate",
      },
      keyframes: {
        glowRed: {
          "0%": { boxShadow: "0 0 15px rgba(239, 68, 68, 0.4)" },
          "100%": { boxShadow: "0 0 30px rgba(239, 68, 68, 0.9)" },
        },
      },
    },
  },
  plugins: [],
};
