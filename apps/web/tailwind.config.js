export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    fontSize: {
      micro: ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.02em' }],
      xs: ['0.75rem', { lineHeight: '1.125rem' }],
      sm: ['0.875rem', { lineHeight: '1.375rem' }],
      base: ['1rem', { lineHeight: '1.5rem' }],
      lg: ['1.125rem', { lineHeight: '1.5rem', letterSpacing: '-0.006em' }],
      xl: ['1.25rem', { lineHeight: '1.625rem', letterSpacing: '-0.011em' }],
      '2xl': ['1.5rem', { lineHeight: '1.875rem', letterSpacing: '-0.018em' }],
      '3xl': ['1.875rem', { lineHeight: '2.25rem', letterSpacing: '-0.022em' }],
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
        read: '40rem',
        app: '90rem',
      },
    },
  },
  plugins: [],
};
