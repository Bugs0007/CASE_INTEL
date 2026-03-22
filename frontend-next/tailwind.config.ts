import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        sidebar: {
          DEFAULT: "#1a1a2e",
          hover: "#252540",
          active: "#16213e",
        },
        primary: {
          DEFAULT: "#e74c3c",
          hover: "#c0392b",
        },
        accent: {
          blue: "#3498db",
          green: "#27ae60",
          purple: "#9b59b6",
          orange: "#e67e22",
        },
        priority: {
          low: "#10b981",
          medium: "#f59e0b",
          high: "#ef4444",
          critical: "#7c3aed",
        },
        status: {
          active: "#10b981",
          pending: "#f59e0b",
          closed: "#6b7280",
          archived: "#9ca3af",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
