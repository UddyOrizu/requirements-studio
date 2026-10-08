/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      colors: {
        // One calm accent; everything else is slate. Control colours follow M10 (blue / amber / white / red).
        accent: { 50: "#eef7f6", 100: "#d5ece9", 500: "#2f7f78", 600: "#256a64", 700: "#1d5550" },
        control: {
          auto: "#DAE8FC", autoLine: "#6C8EBF",
          review: "#FFE6CC", reviewLine: "#D79B00",
          approval: "#F8CECC", approvalLine: "#B85450",
          decision: "#FFF2CC", decisionLine: "#D6B656",
          terminal: "#D5E8D4", terminalLine: "#82B366",
        },
      },
    },
  },
  plugins: [],
};
