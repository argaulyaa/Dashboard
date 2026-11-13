/** @type {import('tailwindcss').Config} */
const themedColor = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // dashboard (legacy: DomainPage, ComponentCard, ControlDrawer, Reservasi)
        bg: themedColor("legacy-bg"),
        panel: themedColor("legacy-panel"),
        "panel-border": themedColor("legacy-panel-border"),
        ink: themedColor("legacy-ink"),
        dim: themedColor("legacy-dim"),
        healthy: "#0e9f6e",
        degraded: "#d97706",
        down: "#dc2626",
        restarting: "#2563eb",

        // Material 3 tokens (login page + app shell baru / Overview)
        primary: themedColor("primary"),
        "primary-container": themedColor("primary-container"),
        "on-primary": themedColor("on-primary"),
        "on-primary-container": themedColor("on-primary-container"),
        "primary-fixed": themedColor("primary-fixed"),
        "primary-fixed-dim": themedColor("primary-fixed-dim"),
        "on-primary-fixed": themedColor("on-primary-fixed"),
        "on-primary-fixed-variant": themedColor("on-primary-fixed-variant"),
        "inverse-primary": themedColor("inverse-primary"),

        secondary: "#006c47",
        "secondary-container": "#82f9be",
        "on-secondary": "#ffffff",
        "on-secondary-container": "#00734c",
        "secondary-fixed": "#82f9be",
        "secondary-fixed-dim": "#65dca4",
        "on-secondary-fixed": "#002113",
        "on-secondary-fixed-variant": "#005235",

        tertiary: "#5e3c00",
        "tertiary-container": "#7d5200",
        "on-tertiary": "#ffffff",
        "on-tertiary-container": "#ffca81",
        "tertiary-fixed": "#ffddb3",
        "tertiary-fixed-dim": "#ffb950",
        "on-tertiary-fixed": "#291800",
        "on-tertiary-fixed-variant": "#624000",

        error: "#ba1a1a",
        "error-container": "#ffdad6",
        "on-error": "#ffffff",
        "on-error-container": "#93000a",

        background: themedColor("background"),
        "on-background": themedColor("on-background"),
        surface: themedColor("surface"),
        "surface-dim": themedColor("surface-dim"),
        "surface-bright": themedColor("surface-bright"),
        "surface-tint": themedColor("surface-tint"),
        "surface-container-lowest": themedColor("surface-container-lowest"),
        "surface-container-low": themedColor("surface-container-low"),
        "surface-container": themedColor("surface-container"),
        "surface-container-high": themedColor("surface-container-high"),
        "surface-container-highest": themedColor("surface-container-highest"),
        "on-surface": themedColor("on-surface"),
        "on-surface-variant": themedColor("on-surface-variant"),
        "surface-variant": themedColor("surface-variant"),
        "inverse-surface": themedColor("inverse-surface"),
        "inverse-on-surface": themedColor("inverse-on-surface"),

        outline: themedColor("outline"),
        "outline-variant": themedColor("outline-variant"),
      },

      fontFamily: {
        sans: ["IBM Plex Sans", "sans-serif"],
        mono: ["IBM Plex Mono", "monospace"],
        display: ["Inter", "sans-serif"],
        "body-lg": ["Inter", "sans-serif"],
        "label-lg": ["Inter", "sans-serif"],
        "label-sm": ["Inter", "sans-serif"],
        "title-lg": ["Inter", "sans-serif"],
        "title-md": ["Inter", "sans-serif"],
        "body-md": ["Inter", "sans-serif"],
        "headline-lg-mobile": ["Inter", "sans-serif"],
        "headline-md": ["Inter", "sans-serif"],
        "headline-lg": ["Inter", "sans-serif"],
        "code-md": ["IBM Plex Mono", "monospace"],
        "display-lg": ["Inter", "sans-serif"],
      },

      fontSize: {
        "body-lg": ["16px", { lineHeight: "24px", fontWeight: "400" }],
        "label-lg": ["14px", { lineHeight: "20px", letterSpacing: "0.01em", fontWeight: "500" }],
        "title-lg": ["20px", { lineHeight: "28px", fontWeight: "600" }],
        "headline-lg-mobile": ["24px", { lineHeight: "32px", fontWeight: "600" }],
        "title-md": ["16px", { lineHeight: "24px", fontWeight: "600" }],
        "body-md": ["14px", { lineHeight: "20px", fontWeight: "400" }],
        "headline-md": ["24px", { lineHeight: "32px", fontWeight: "600" }],
        "headline-lg": ["32px", { lineHeight: "40px", letterSpacing: "-0.01em", fontWeight: "600" }],
        "label-sm": ["12px", { lineHeight: "16px", letterSpacing: "0.04em", fontWeight: "600" }],
        "code-md": ["13px", { lineHeight: "18px", letterSpacing: "0em", fontWeight: "400" }],
        "display-lg": ["48px", { lineHeight: "56px", letterSpacing: "-0.02em", fontWeight: "700" }],
      },

      spacing: {
        base: "4px",
        "stack-gap": "16px",
        "sidebar-width": "280px",
        gutter: "24px",
        "container-padding-desktop": "32px",
        "container-padding-mobile": "16px",
      },

      borderRadius: {
        DEFAULT: "0.25rem",
        lg: "0.5rem",
        xl: "0.75rem",
        full: "9999px",
      },

      keyframes: {
        travel: {
          from: { left: "-20%" },
          to: { left: "100%" },
        },
        dash: {
          to: { strokeDashoffset: "-1000" },
        },
      },

      animation: {
        travel: "travel 2.2s linear infinite",
        dash: "dash 20s linear infinite",
      },
    },
  },
  plugins: [require("@tailwindcss/forms"), require("@tailwindcss/container-queries")],
};
