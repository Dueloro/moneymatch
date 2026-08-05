/** @type {import('tailwindcss').Config} */
// Colours map to the CSS custom properties in src/styles/index.css (the design
// tokens from 16-ui-revamp-plan §2) so the palette lives in one place.
//
// The default font scale is *overridden* rather than extended: existing markup
// keeps using text-xs / text-sm / text-lg and snaps to the new ramp, which is
// how one scale gets enforced without rewriting every file.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    fontSize: {
      micro: ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.02em' }], // 11
      xs: ['0.75rem', { lineHeight: '1.125rem' }], // 12  subline, meta
      sm: ['0.875rem', { lineHeight: '1.375rem' }], // 14  body default
      base: ['1rem', { lineHeight: '1.5rem' }], // 16  lead
      lg: ['1.125rem', { lineHeight: '1.5rem', letterSpacing: '-0.006em' }], // 18
      xl: ['1.25rem', { lineHeight: '1.625rem', letterSpacing: '-0.011em' }], // 20
      '2xl': ['1.5rem', { lineHeight: '1.875rem', letterSpacing: '-0.018em' }], // 24
      '3xl': ['1.875rem', { lineHeight: '2.25rem', letterSpacing: '-0.022em' }], // 30
    },
    extend: {
      colors: {
        bg: 'var(--bg)',
        panel: 'var(--panel)',
        'panel-raised': 'var(--panel-raised)',
        overlay: 'var(--overlay)',
        hairline: 'var(--hairline)',
        'line-strong': 'var(--line-strong)',
        text: 'var(--text)',
        'text-secondary': 'var(--text-secondary)',
        'text-tertiary': 'var(--text-tertiary)',
        green: 'var(--green)',
        'green-dim': 'var(--green-dim)',
        action: 'var(--action)',
        live: 'var(--live)',
        red: 'var(--red)',
        warn: 'var(--warn)',
        focus: 'var(--focus)',
      },
      borderRadius: {
        pill: 'var(--radius-pill)',
        card: 'var(--radius-card)',
        inset: 'var(--radius-inset)',
      },
      boxShadow: {
        overlay: 'var(--shadow-overlay)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      maxWidth: {
        // One rule for column width: `read` for prose-and-list pages, `app` for
        // the shell container. Everything else is a grid span.
        read: '40rem', // 640
        app: '90rem', // 1440
      },
    },
  },
  plugins: [],
};
