/** @type {import('tailwindcss').Config} */
// Colors map to the CSS custom properties in src/styles/index.css (the design
// tokens from 02-design-system §1) so the palette lives in one place.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        panel: 'var(--panel)',
        'panel-raised': 'var(--panel-raised)',
        hairline: 'var(--hairline)',
        text: 'var(--text)',
        'text-secondary': 'var(--text-secondary)',
        'text-tertiary': 'var(--text-tertiary)',
        green: 'var(--green)',
        'green-dim': 'var(--green-dim)',
        red: 'var(--red)',
      },
      borderRadius: {
        pill: 'var(--radius-pill)',
        card: 'var(--radius-card)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
};
