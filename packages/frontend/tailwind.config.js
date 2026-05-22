/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // TradingView-accurate palette
        surface: '#131722',   // main background
        panel:   '#1e222d',   // panels / sidebars
        panel2:  '#2a2e39',   // secondary panels, inputs
        border:  '#2a2e39',   // dividers and borders
        accent:  '#2962ff',   // action blue (TV brand color)
        buy:     '#26a69a',   // bullish teal-green
        sell:    '#ef5350',   // bearish red
        hold:    '#b2b5be',   // neutral grey (TV text-secondary)
        muted:   '#787b86',   // dimmed text
      },
      fontFamily: {
        sans: ['"Trebuchet MS"', 'system-ui', '-apple-system', 'Roboto', '"Segoe UI"', 'sans-serif'],
        mono: ['"Courier New"', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
