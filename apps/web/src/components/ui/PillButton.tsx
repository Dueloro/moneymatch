import type { ButtonHTMLAttributes } from 'react';

type Variant = 'primary' | 'secondary' | 'outline' | 'text' | 'danger';
type Size = 'sm' | 'md' | 'lg';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-action text-bg hover:opacity-90 active:opacity-80',
  secondary:
    'bg-panel-raised text-text border border-hairline hover:border-line-strong',
  outline: 'border border-hairline text-text hover:border-line-strong',
  text: 'text-text-secondary hover:text-text',
  danger: 'border border-red/40 text-red hover:border-red hover:bg-red/10',
};

const SIZES: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs touch:min-h-11',
  md: 'px-4 py-2 text-sm touch:min-h-11',
  lg: 'px-5 py-3 text-sm touch:min-h-11',
};

interface PillButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  fullWidth?: boolean;
}

export function PillButton({
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  className = '',
  type = 'button',
  ...props
}: PillButtonProps) {
  return (
    <button
      type={type}
      className={[
        'inline-flex items-center justify-center gap-2 rounded-pill font-semibold',
        'transition-colors disabled:cursor-not-allowed disabled:opacity-40',
        SIZES[size],
        VARIANTS[variant],
        fullWidth ? 'w-full' : '',
        className,
      ].join(' ')}
      {...props}
    />
  );
}
