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
        // ── Incept: semantic tokens matching original Incept-ai-workspace ──────
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
        intersight: {
          primary:      "#3a86ff",
          primaryHover: "#2872f0",
          primarySoft:  "#EEF4FF",
          primaryBorder:"#C7DEFF",
          mist:         "#F4F7FF",
          lavender:     "#EEF2FF",
          pearl:        "#F8FAFF",
          sky:          "#EDF4FF",
          text:         "#1F2230",
          secondary:    "#586174",
          tertiary:     "#8B92A8",
          border:       "#E0E8F5",
          softBorder:   "#EAF0FA",
          success:      "#2FA66A",
          warning:      "#E59A2F",
          danger:       "#D85C5C",
          purple:       "#8338ec",
          teal:         "#4FA4D9"
        }
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
