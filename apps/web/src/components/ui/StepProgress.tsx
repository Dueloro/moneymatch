/** 3-segment progress bar for the sign-in flow. */
export function StepProgress({ step, total = 3 }: { step: number; total?: number }) {
  return (
    <div className="flex gap-1.5" aria-label={`Step ${step} of ${total}`}>
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={[
            'h-1 w-10 rounded-pill',
            i < step ? 'bg-action' : 'bg-hairline',
          ].join(' ')}
        />
      ))}
    </div>
  );
}
