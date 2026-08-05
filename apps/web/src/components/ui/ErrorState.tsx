import { PillButton } from './PillButton';

/** Shown when a query fails, so a surface degrades to an honest, retryable
 * message instead of a silently empty shell. Says what broke and what to do. */
export function ErrorState({
  title = 'Something went wrong',
  subline = 'We could not load this. Try again.',
  onRetry,
}: {
  title?: string;
  subline?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-2 rounded-card border border-dashed border-red/30 px-6 py-16 text-center"
      data-testid="error-state"
    >
      <p className="text-base font-semibold text-text">{title}</p>
      <p className="max-w-sm text-sm text-text-secondary">{subline}</p>
      {onRetry && (
        <div className="mt-4">
          <PillButton variant="outline" onClick={onRetry}>
            Try again
          </PillButton>
        </div>
      )}
    </div>
  );
}
