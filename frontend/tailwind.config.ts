import type { Config } from "tailwindcss";

/**
 * Design tokens for a trust instrument, not a marketing page (04-frontend.md §7).
 * One PASS colour, one FAIL colour, everything else neutral; severity steps through
 * graded warmth so a critical reads hotter than a medium at a glance.
 *
 * Every value resolves to a CSS variable defined in globals.css, which is what makes
 * light and dark a single definition instead of two parallel sets of classes.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "var(--surface)",
          2: "var(--surface-2)",
          3: "var(--surface-3)",
        },
        line: {
          DEFAULT: "var(--border)",
          strong: "var(--border-strong)",
        },
        body: "var(--text)",
        muted: "var(--text-2)",
        faint: "var(--text-3)",

        // Inverted pair for primary buttons — flips with the theme automatically.
        ink: "var(--text)",
        paper: "var(--surface)",

        pass: {
          fg: "var(--pass-fg)",
          bg: "var(--pass-bg)",
          border: "var(--pass-border)",
        },
        fail: {
          fg: "var(--fail-fg)",
          bg: "var(--fail-bg)",
          border: "var(--fail-border)",
        },
        exempt: {
          fg: "var(--exempt-fg)",
          bg: "var(--exempt-bg)",
          border: "var(--exempt-border)",
        },
        warn: {
          fg: "var(--warn-fg)",
          bg: "var(--warn-bg)",
          border: "var(--warn-border)",
        },
        sev: {
          critical: "var(--sev-critical)",
          high: "var(--sev-high)",
          medium: "var(--sev-medium)",
          low: "var(--sev-low)",
        },
        track: "var(--track)",
      },
      fontFamily: {
        // Open Sans for body/UI, Raleway for headings. Both self-hosted via next/font,
        // with system fallbacks so nothing reflows if a face fails to load.
        sans: [
          "var(--font-sans)",
          "ui-sans-serif",
          "system-ui",
          "Segoe UI",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        display: [
          "var(--font-display)",
          "var(--font-sans)",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
