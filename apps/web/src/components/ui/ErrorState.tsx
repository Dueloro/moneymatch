import { PillButton } from './PillButton';

/** Shown when a query fails, so a surface degrades to an honest, retryable
 * message instead of a silently empty shell. */
export function ErrorState({
  title = 'Something went wrong',
  subline = 'We could not load this. Please try again.',
  onRetry,
}: {
  title?: string;
  subline?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-2 py-20 text-center"
      data-testid="error-state"
    >
      <p className="text-lg font-semibold text-text">{title}</p>
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
