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
        deep: "var(--mm-bg-deep)",
        "text-on-deep": "var(--mm-text-on-deep)",
        muted: "var(--mm-muted)",
        accent: "var(--mm-accent)",
        "on-accent": "var(--mm-on-accent)",
        home: "var(--mm-home)",
        away: "var(--mm-away)",
        good: "var(--mm-good)",
        warn: "var(--mm-warn)",
      },
      keyframes: {
        rise: { from: { transform: "translateY(14px)", opacity: "0" }, to: { transform: "none", opacity: "1" } },
      },
      animation: { rise: "rise var(--mm-dur-slow) var(--mm-ease) both" },
      fontFamily: {
        display: "var(--mm-font-display)",
        body: "var(--mm-font-body)",
      },
    },
  },
  plugins: [],
} satisfies Config;
