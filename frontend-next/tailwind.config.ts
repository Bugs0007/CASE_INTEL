import type { Config } from "tailwindcss";

// Every hex value below is read directly from the Claude Design bundle's
// "Design System.dc.html" (color swatches + typography section) plus the
// literal inline styles used across Dashboard/Cases/CaseDetail/Calendar/
// Documents/Login .dc.html -- not approximated from memory.
const config: Config = {
  content: [
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        page: "#f6f7f9",
        primary: {
          DEFAULT: "#323b83", // Primary 600 -- default
          hover: "#272e68", // Primary 700 -- hover
          active: "#1d2350", // Primary 800 -- active
          light: "#dde3f7", // Primary 100 -- active-nav bg
        },
        destructive: {
          DEFAULT: "#d1372e", // Red 600
          hover: "#b32e26", // Red 700 -- hover
        },
        // Overrides Tailwind's default gray scale with the design system's
        // own Neutrals swatch (25/100/200/300/400/500/700/900 given
        // explicitly; 600/800 interpolated from the exact body-text/
        // meta-text colors used pervasively across every screen's inline
        // styles: #545b6c for meta/secondary text, #23273e for base body
        // text).
        gray: {
          50: "#fafafb", // Gray 25
          100: "#eceef2", // Gray 100
          200: "#dde1e8", // Gray 200
          300: "#c3c9d4", // Gray 300
          400: "#9aa1b2", // Gray 400
          500: "#717889", // Gray 500
          600: "#545b6c", // Meta/13 text color (between Gray 500 and 700)
          700: "#383e4e", // Gray 700
          800: "#23273e", // universal base body-text color on every screen
          900: "#14171f", // Gray 900 -- headings
        },
        semantic: {
          success: { bg: "#e9f7f1", text: "#146349" },
          warning: { bg: "#fdf3e0", text: "#92610f" },
          attention: { bg: "#fdf0e4", text: "#9a4a12" },
          critical: { bg: "#f3ecfb", text: "#6b3aa0" },
          info: { bg: "#ebf3fb", text: "#2f6fb0" },
          neutral: { bg: "#eceef2", text: "#4b5468" },
          error: { bg: "#fdecec", text: "#b32e26" },
        },
      },
      fontFamily: {
        sans: [
          "var(--font-public-sans)",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        // Design System.dc.html's literal type scale.
        "page-title": ["32px", { lineHeight: "38px", fontWeight: "700" }],
        "section-title": ["20px", { lineHeight: "1.3", fontWeight: "600" }],
        "card-title": ["16px", { lineHeight: "1.4", fontWeight: "600" }],
        body: ["15px", { lineHeight: "1.6", fontWeight: "400" }],
        meta: ["13px", { lineHeight: "1.5", fontWeight: "400" }],
        eyebrow: [
          "12px",
          { lineHeight: "1.4", fontWeight: "700", letterSpacing: "0.06em" },
        ],
      },
      keyframes: {
        "chat-indeterminate": {
          "0%": { transform: "translateX(-100%)" },
          "50%": { transform: "translateX(150%)" },
          "100%": { transform: "translateX(-100%)" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-in-right": {
          "0%": { transform: "translateX(100%)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
      },
      animation: {
        "chat-indeterminate": "chat-indeterminate 1.2s ease-in-out infinite",
        "fade-up": "fade-up 0.25s ease-out both",
        "fade-in": "fade-in 0.2s ease-out both",
        "slide-in-right": "slide-in-right 0.3s ease-out both",
      },
    },
  },
  plugins: [],
};

export default config;
