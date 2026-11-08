export type Variant = 'primary' | 'secondary' | 'outline' | 'text' | 'danger';
export type Size = 'sm' | 'md' | 'lg';

export const VARIANTS: Record<Variant, string> = {
  primary: 'bg-action text-bg hover:opacity-90 active:opacity-80',
  secondary:
    'bg-panel-raised text-text border border-hairline hover:border-line-strong',
  outline: 'border border-hairline text-text hover:border-line-strong',
  text: 'text-text-secondary hover:text-text',
  danger: 'border border-red/40 text-red hover:border-red hover:bg-red/10',
};

export const SIZES: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs touch:min-h-11',
  md: 'px-4 py-2 text-sm touch:min-h-11',
  lg: 'px-5 py-3 text-sm touch:min-h-11',
};

/** The pill look for a link that acts as a button (an `<a>` can't hold a `<button>`). */
export function pillClassName({
  variant = 'primary',
  size = 'md',
  fullWidth = false,
}: { variant?: Variant; size?: Size; fullWidth?: boolean } = {}): string {
  return [
    'inline-flex items-center justify-center gap-2 rounded-pill font-semibold transition-colors',
    SIZES[size],
    VARIANTS[variant],
    fullWidth ? 'w-full' : '',
  ].join(' ');
}
