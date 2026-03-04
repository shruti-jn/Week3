import type { Config } from "tailwindcss";

/**
 * Tailwind CSS configuration — extends defaults with LegacyLens terminal theme.
 *
 * Color palette is inspired by classic green-phosphor terminal monitors.
 * Everything dark, accents in neon green, monospace everywhere.
 */
const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        terminal: {
          bg: "#0a0a0a",
          surface: "#111111",
          border: "#1f1f1f",
          "border-bright": "#2d2d2d",
          accent: "#00ff88",
          "accent-dim": "#00cc6a",
          "accent-dark": "#003d21",
          text: "#e2e8f0",
          muted: "#6b7280",
          dim: "#374151",
          error: "#ff4444",
          warn: "#ffaa00",
        },
      },
      fontFamily: {
        mono: [
          "JetBrains Mono",
          "Fira Code",
          "Cascadia Code",
          "Menlo",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "Courier New",
          "monospace",
        ],
      },
      animation: {
        blink: "blink 1s step-end infinite",
        "fade-in": "fade-in 0.3s ease-out",
        "slide-up": "slide-up 0.3s ease-out",
      },
      keyframes: {
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      boxShadow: {
        "accent-sm": "0 0 8px rgba(0, 255, 136, 0.2)",
        "accent-md": "0 0 20px rgba(0, 255, 136, 0.2)",
        "accent-lg": "0 0 40px rgba(0, 255, 136, 0.15)",
      },
    },
  },
  plugins: [],
};

export default config;
