import type { ButtonHTMLAttributes } from 'react';

import { SIZES, VARIANTS, type Size, type Variant } from './pillClass';

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
