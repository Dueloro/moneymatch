const token =
  (name) =>
  ({ opacityValue }) =>
    opacityValue === undefined || opacityValue === '1'
      ? `var(--${name})`
      : `color-mix(in srgb, var(--${name}) calc(${opacityValue} * 100%), transparent)`;

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
        bg: token('bg'),
        panel: token('panel'),
        'panel-raised': token('panel-raised'),
        overlay: token('overlay'),
        hairline: token('hairline'),
        'line-strong': token('line-strong'),
        text: token('text'),
        'text-secondary': token('text-secondary'),
        'text-tertiary': token('text-tertiary'),
        green: token('green'),
        'green-dim': token('green-dim'),
        action: token('action'),
        live: token('live'),
        red: token('red'),
        warn: token('warn'),
        focus: token('focus'),
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
        mono: ['var(--font-mono)'],
      },
      maxWidth: {
        read: '40rem',
        app: '90rem',
      },
    },
  },
  plugins: [],
};
