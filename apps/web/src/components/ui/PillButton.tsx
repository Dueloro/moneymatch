import type { ButtonHTMLAttributes } from 'react';

type Variant = 'primary' | 'secondary' | 'outline' | 'text';

const VARIANTS: Record<Variant, string> = {
  // Primary = solid green, black text. Secondary = white, black text.
  // Outline = hairline border, white text. Text = bare label. (02-design §1)
  primary: 'bg-green text-black hover:opacity-90',
  secondary: 'bg-text text-black hover:opacity-90',
  outline: 'border border-hairline text-text hover:border-text-secondary',
  text: 'text-text-secondary hover:text-text',
};

interface PillButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  fullWidth?: boolean;
}

export function PillButton({
  variant = 'primary',
  fullWidth = false,
  className = '',
  ...props
}: PillButtonProps) {
  return (
    <button
      className={[
        'inline-flex items-center justify-center rounded-pill px-5 py-2.5',
        'text-sm font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed',
        VARIANTS[variant],
        fullWidth ? 'w-full' : '',
        className,
      ].join(' ')}
      {...props}
    />
  );
}
