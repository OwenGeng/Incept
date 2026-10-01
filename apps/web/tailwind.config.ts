import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        // ── LinglongLab: semantic tokens matching original LinglongLab-ai-workspace ──────
        // CSS variables are defined in .incept-scope in globals.css (hex values).
        // Direct var() references — solid colors work perfectly.
        // Note: opacity modifiers (bg-muted/60) are not supported with this format.
        background:  "var(--background)",
        foreground:  "var(--foreground)",
        card: {
          DEFAULT:    "var(--card)",
          foreground: "var(--card-foreground)",
        },
        popover: {
          DEFAULT:    "var(--popover)",
          foreground: "var(--popover-foreground)",
        },
        primary: {
          DEFAULT:    "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT:    "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        muted: {
          DEFAULT:    "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        accent: {
          DEFAULT:    "var(--accent)",
          foreground: "var(--accent-foreground)",
        },
        destructive: {
          DEFAULT:    "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        border:           "var(--border)",
        input:            "var(--input)",
        ring:             "var(--ring)",
        "soft-accent":    "var(--soft-accent)",
        "ai-accent":      "var(--ai-accent)",
        "ai-accent-soft": "var(--ai-accent-soft)",
        "border-soft":    "var(--border-soft)",
        "border-strong":  "var(--border-strong)",
        success:          "var(--success)",
        "success-soft":   "var(--success-soft)",
        warning:          "var(--warning)",
        "warning-soft":   "var(--warning-soft)",
        "danger-soft":    "var(--danger-soft)",

        brand: {
          blue:   "#3a86ff",
          purple: "#8338ec",
          pink:   "#ff006e",
          orange: "#fb5607",
          yellow: "#ffbe0b",
        },
      },
      boxShadow: {
        shell: "0 20px 50px rgba(20,30,48,0.10)",
        card:  "0 4px 20px rgba(58,134,255,0.07)",
        "card-hover": "0 8px 32px rgba(58,134,255,0.13)",
      },
      borderRadius: {
        shell: "32px",
        canvas: "28px"
      },
      backdropBlur: {
        shell: "20px"
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"]
      }
    }
  },
  plugins: []
};

export default config;
