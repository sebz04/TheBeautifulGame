import type { Config } from "tailwindcss";

// Colors come from the CSS variables in src/design/tokens.css (set per club at runtime).
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--mm-bg)",
        surface: "var(--mm-surface)",
        text: "var(--mm-text)",
        "text-on-bg": "var(--mm-text-on-bg)",
        muted: "var(--mm-muted)",
        accent: "var(--mm-accent)",
        "on-accent": "var(--mm-on-accent)",
        home: "var(--mm-home)",
        away: "var(--mm-away)",
        good: "var(--mm-good)",
        warn: "var(--mm-warn)",
      },
      fontFamily: {
        display: "var(--mm-font-display)",
        body: "var(--mm-font-body)",
      },
    },
  },
  plugins: [],
} satisfies Config;
