import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';

/**
 * Styled form controls. The inventory found native browser checkboxes, selects
 * and radios leaking through on sign-in and in the challenge dialog, which is
 * the fastest way to make a product look unfinished. These give every control
 * one shared treatment and one focus behaviour.
 */

const CONTROL =
  'w-full rounded-pill border border-hairline bg-panel-raised px-4 py-2.5 text-sm text-text ' +
  'transition-colors placeholder:text-text-tertiary hover:border-line-strong ' +
  'focus:border-line-strong disabled:opacity-40';

export function TextInput({
  className = '',
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={[CONTROL, className].join(' ')} {...props} />;
}

export function TextArea({
  className = '',
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={[CONTROL, 'resize-none rounded-inset leading-relaxed', className].join(
        ' ',
      )}
      {...props}
    />
  );
}

/** Native select with the arrow drawn by us, so it matches on every platform. */
export function Select({
  className = '',
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select
        className={[CONTROL, 'appearance-none pr-10', className].join(' ')}
        {...props}
      >
        {children}
      </select>
      <svg
        viewBox="0 0 24 24"
        aria-hidden
        className="pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-text-secondary"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
      >
        <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

/** A label above a control, with optional hint and error lines. */
export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-text-secondary">{label}</span>
      {children}
      {hint && !error && <span className="text-xs text-text-tertiary">{hint}</span>}
      {error && <span className="text-xs text-red">{error}</span>}
    </label>
  );
}

/** Checkbox drawn as a real box we control. Keeps the native input for a11y. */
export function Checkbox({
  checked,
  onChange,
  children,
  disabled = false,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label
      className={[
        'flex cursor-pointer items-start gap-3 text-sm text-text-secondary',
        disabled ? 'cursor-not-allowed opacity-40' : '',
      ].join(' ')}
    >
      <span className="relative mt-0.5 inline-flex">
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          className="peer h-5 w-5 shrink-0 appearance-none rounded-[6px] border border-hairline bg-panel-raised transition-colors hover:border-line-strong checked:border-action checked:bg-action"
        />
        <svg
          viewBox="0 0 24 24"
          aria-hidden
          className="pointer-events-none absolute inset-0 m-auto h-3.5 w-3.5 text-bg opacity-0 peer-checked:opacity-100"
          fill="none"
        >
          <path
            d="M5 12.5 10 17l9-10"
            stroke="currentColor"
            strokeWidth={3}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span>{children}</span>
    </label>
  );
}

/** Radio row used by the challenge dialog's market list. */
export function RadioRow({
  checked,
  onSelect,
  name,
  children,
}: {
  checked: boolean;
  onSelect: () => void;
  name: string;
  children: ReactNode;
}) {
  return (
    <label
      className={[
        'flex cursor-pointer items-center gap-3 rounded-inset px-3 py-2.5 transition-colors',
        checked ? 'bg-panel-raised text-text' : 'text-text-secondary hover:text-text',
      ].join(' ')}
    >
      <span className="relative inline-flex">
        <input
          type="radio"
          name={name}
          checked={checked}
          onChange={onSelect}
          className="peer h-4 w-4 shrink-0 appearance-none rounded-full border border-hairline bg-panel-raised transition-colors checked:border-action"
        />
        <span className="pointer-events-none absolute inset-0 m-auto h-2 w-2 rounded-full bg-action opacity-0 peer-checked:opacity-100" />
      </span>
      <span className="text-sm">{children}</span>
    </label>
  );
}
