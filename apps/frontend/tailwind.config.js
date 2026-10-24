/** @type {import('tailwindcss').Config} */
// Madison Technologies brand tokens, taken from madison-technologies.com (index CSS, logo, favicon). Usage rules: docs/BRAND.md
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Madison cyan (--lp-brand: #48c6fd): logo, primary buttons, active navigation. Too light for text on white; use 600/700 there.
        brand: {
          50: "#EBF8FF",
          100: "#D4F1FF",
          200: "#A9E4FE",
          300: "#6DD4FF",
          400: "#5DD0FF",
          500: "#48C6FD",
          600: "#006BB8",
          700: "#005A99",
          800: "#00467A",
        },
        // Site destructive red (--destructive: #d4183d): CRITICAL, confirmed violations, errors, delete.
        danger: {
          50: "#FEF1F3",
          100: "#FCDDE2",
          200: "#F9B4C0",
          300: "#F4899B",
          400: "#EC4D67",
          500: "#D4183D",
          600: "#B3122F",
          700: "#921028",
          800: "#730C1F",
        },
        // Navy surfaces (--lp-bg-primary, --lp-bg-secondary): sidebar, dark cards, toasts, overlays on camera frames.
        ink: {
          DEFAULT: "#0A1525",
          raised: "#0D1F35",
          edge: "#1E3350",
          field: "#2B4466",
        },
        paper: "#F2F5F9",
        surface: "#FFFFFF",
        subtle: "#F7F9FC",
        muted: "#EFF3F8",
        well: "#E3E9F1",
        line: {
          DEFAULT: "#E0E6EE",
          soft: "#EDF1F6",
          muted: "#E6EBF2",
          strong: "#CBD5E1",
        },
        // Text on light surfaces, slate tinted towards the navy; 900 is the navy itself.
        graphite: {
          300: "#A0ABBB",
          400: "#7A869A",
          500: "#5A677B",
          600: "#475569",
          700: "#334155",
          800: "#1F2A3C",
          900: "#0A1525",
        },
        // Text on navy surfaces.
        fog: {
          50: "#F4F7FB",
          100: "#E1E8F0",
          300: "#AEBBCC",
          500: "#8392A7",
        },
        success: {
          50: "#E8F7EE",
          200: "#BDE5CC",
          600: "#1E9E57",
          700: "#157A42",
          900: "#0E5530",
        },
        // Orange: HIGH severity, middling AI confidence.
        warn: {
          50: "#FFF3E6",
          500: "#F78F24",
          700: "#9A4A00",
        },
        // Indigo, well apart from the cyan: NEW incidents, zones that moved with the camera, the zone being drawn.
        info: {
          50: "#EEF0FD",
          500: "#4F5FE0",
          700: "#3240B0",
        },
        toggle: "#C5CED9",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Segoe UI", "Helvetica Neue", "Arial", "sans-serif"],
        // The site sets headings in the same face as body text, only heavier.
        display: ["var(--font-sans)", "Segoe UI", "Arial", "sans-serif"],
        mono: ["var(--font-mono)", "Consolas", "monospace"],
      },
      backgroundImage: {
        // Cyan light from the top-right corner of a navy card, as behind the site's hero.
        glow: "radial-gradient(120% 90% at 100% 0%, rgba(72,198,253,.20), transparent 60%)",
        hero: "radial-gradient(70% 55% at 85% 20%, rgba(72,198,253,.28), transparent 70%), linear-gradient(160deg, #0D1F35 0%, #0A1525 55%, #0A0F14 100%)",
        // The site's .section-gradient-text: the "MADISON" wordmark and highlighted words.
        "brand-text": "linear-gradient(135deg, #5DD0FF 0%, #48C6FD 35%, #29B3F5 65%, #1AA0E8 100%)",
        dots: "radial-gradient(rgba(255,255,255,.22) 1px, transparent 1.4px)",
        stripes: "repeating-linear-gradient(135deg, #0D1F35 0 10px, #13283F 10px 20px)",
        bars: "linear-gradient(180deg, #AEB9C7, #7F8DA1)",
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
