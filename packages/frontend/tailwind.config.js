/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: '#0f1117',
        panel: '#1a1d27',
        border: '#2a2d3a',
        accent: '#6366f1',
        buy: '#22c55e',
        sell: '#ef4444',
        hold: '#f59e0b',
      },
    },
  },
  plugins: [],
}
