import type { Config } from "tailwindcss";

// Every color/radius/shadow/font token below is a CSS custom property from
// app/case-intel-theme.css (imported globally, ahead of this config's own
// output, in app/layout.tsx) rather than a duplicated raw value -- so a
// `bg-primary`, `text-gray-600`, `rounded-lg`, or `font-sans` anywhere in
// the app automatically tracks the design tokens instead of drifting from
// them. Status/priority chips prefer the `.ci-chip--*` primitives directly
// (see components/ui/badge.tsx) rather than these color utilities, since
// theme.css's chip is purpose-built for the ok/pending/alert three-way.
const config: Config = {
  content: [
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        page: "var(--ci-paper)",
        surface: "var(--ci-surface)",
        primary: {
          DEFAULT: "var(--ci-ink)", // ci-btn--solid's resting state
          hover: "var(--ci-seal)", // ci-btn--solid's hover state
          active: "var(--ci-seal)",
          light: "var(--ci-seal-soft)",
        },
        destructive: {
          DEFAULT: "var(--ci-seal)",
          hover: "var(--ci-seal)",
        },
        // Collapses Tailwind's default 10-step gray scale onto theme.css's
        // 5-step ink scale (ci-ink / ci-ink-70 / ci-ink-45 / ci-ink-14 /
        // ci-ink-08) rather than keeping a separate, unrelated gray ramp --
        // every bg-gray-*/text-gray-* usage across the app now resolves to
        // the same ink tokens the primitives (.ci-card, .ci-table, etc) use.
        gray: {
          50: "var(--ci-ink-08)",
          100: "var(--ci-ink-08)",
          200: "var(--ci-ink-14)",
          300: "var(--ci-ink-14)",
          400: "var(--ci-ink-45)",
          500: "var(--ci-ink-45)",
          600: "var(--ci-ink-70)",
          700: "var(--ci-ink-70)",
          800: "var(--ci-ink)",
          900: "var(--ci-ink)",
        },
        // The 3-way status meaning, for anything that needs a bare color
        // rather than a full .ci-chip (icons, dots, thin accents). Status
        // chips themselves should use .ci-chip--ok/--pending/--alert/--none.
        status: {
          ok: "var(--ci-listed)",
          "ok-soft": "var(--ci-listed-soft)",
          pending: "var(--ci-warn)",
          "pending-soft": "var(--ci-warn-soft)",
          alert: "var(--ci-seal)",
          "alert-soft": "var(--ci-seal-soft)",
        },
        // Same underlying color as status.alert (--ci-seal is deliberately
        // dual-purpose in theme.css: "primary accent, destructive, active
        // nav") but named for its other job -- drawing attention to
        // something without claiming it's a failure/alert, e.g. the "your
        // side" emphasis block on an order summary.
        accent: {
          DEFAULT: "var(--ci-seal)",
          soft: "var(--ci-seal-soft)",
        },
      },
      borderRadius: {
        // theme.css is deliberately near-square ("a register, not a toy") --
        // this replaces Tailwind's default rounded scale everywhere except
        // `rounded-full`, which stays for circular chrome (avatars, dots,
        // notification-count pills) that isn't a status/content surface.
        none: "0px",
        sm: "var(--ci-radius)",
        DEFAULT: "var(--ci-radius)",
        md: "var(--ci-radius)",
        lg: "var(--ci-radius-lg)",
        xl: "var(--ci-radius-lg)",
        "2xl": "var(--ci-radius-lg)",
        "3xl": "var(--ci-radius-lg)",
        full: "9999px",
      },
      boxShadow: {
        card: "var(--ci-shadow)",
      },
      fontFamily: {
        sans: ["var(--ci-sans)"],
        serif: ["var(--ci-serif)"],
        mono: ["var(--ci-mono)"],
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
  plugins: [require("@tailwindcss/container-queries")],
};

export default config;
