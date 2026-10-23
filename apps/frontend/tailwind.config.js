/** @type {import('tailwindcss').Config} */
// Viettel IDC brand tokens, taken from viettelidc.com.vn (variable.css, styles.css, custom.css). Usage rules: docs/BRAND.md
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Viettel red (--red: #ee0033): primary buttons, active navigation, links, CRITICAL.
        brand: {
          50: "#FFF0F3",
          100: "#FFDDE4",
          200: "#FFB8C6",
          300: "#FF7A93",
          400: "#FF3D63",
          500: "#EE0033",
          600: "#D1002D",
          700: "#AD0025",
          800: "#87001D",
        },
        // Charcoal surfaces: dark cards, toasts, overlays on camera frames.
        ink: {
          DEFAULT: "#23262A",
          raised: "#2C3034",
          edge: "#3B3F45",
          field: "#4A4F56",
        },
        paper: "#F4F5F7",
        surface: "#FFFFFF",
        subtle: "#F8F9FA",
        muted: "#F2F3F5",
        well: "#E9EBEE",
        line: {
          DEFAULT: "#E1E1E1",
          soft: "#EEEEEE",
          muted: "#E8E8E8",
          strong: "#D2D4D7",
        },
        // Text on light surfaces (900 --title, 800 --content, 700 --new-black).
        graphite: {
          300: "#A5A9AE",
          400: "#7D8288",
          500: "#63686E",
          600: "#4F5459",
          700: "#44494D",
          800: "#383838",
          900: "#252525",
        },
        // Text on charcoal surfaces.
        fog: {
          50: "#F7F7F8",
          100: "#E4E6E8",
          300: "#B3B7BC",
          500: "#8D9298",
        },
        success: {
          50: "#E8F7EE",
          200: "#BDE5CC",
          600: "#1E9E57",
          700: "#157A42",
          900: "#0E5530",
        },
        // Site orange (#f78f24): HIGH severity, middling AI confidence.
        warn: {
          50: "#FFF3E6",
          500: "#F78F24",
          700: "#9A4A00",
        },
        // Site blue (--primary: #4199e4): NEW incidents, zones that moved with the camera.
        info: {
          50: "#EAF3FC",
          500: "#4199E4",
          700: "#1D5FA6",
        },
        toggle: "#C9CCD0",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Segoe UI", "Helvetica Neue", "Arial", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "Segoe UI", "Arial", "sans-serif"],
        mono: ["var(--font-mono)", "Consolas", "monospace"],
      },
      backgroundImage: {
        // Red light from the top-right corner of a charcoal card, as on the site's dark banners.
        glow: "radial-gradient(120% 90% at 100% 0%, rgba(238,0,51,.30), transparent 60%)",
        "brand-sweep": "linear-gradient(135deg, #FF1A4B 0%, #EE0033 45%, #AD0025 100%)",
        dots: "radial-gradient(rgba(255,255,255,.22) 1px, transparent 1.4px)",
        stripes: "repeating-linear-gradient(135deg, #2C3034 0 10px, #33373C 10px 20px)",
        bars: "linear-gradient(180deg, #A9AEB4, #7D8288)",
      },
      keyframes: {
        "live-pulse": {
          "0%": { boxShadow: "0 0 0 0 rgba(30,158,87,.55)" },
          "70%": { boxShadow: "0 0 0 8px rgba(30,158,87,0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(30,158,87,0)" },
        },
        "demo-pulse": {
          "0%": { boxShadow: "0 0 0 0 rgba(217,119,6,.55)" },
          "70%": { boxShadow: "0 0 0 8px rgba(217,119,6,0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(217,119,6,0)" },
        },
        rec: { "0%, 100%": { opacity: "1" }, "50%": { opacity: ".25" } },
        scan: { "0%": { top: "-3%" }, "100%": { top: "103%" } },
        "slide-in": { from: { opacity: "0", transform: "translateX(24px)" }, to: { opacity: "1", transform: "none" } },
      },
      animation: {
        "live-pulse": "live-pulse 2s infinite",
        "demo-pulse": "demo-pulse 2s infinite",
        rec: "rec 1.4s ease-in-out infinite",
        scan: "scan 4.5s linear infinite",
        "slide-in": "slide-in .28s cubic-bezier(.2,.8,.2,1)",
      },
    },
  },
  plugins: [],
};
