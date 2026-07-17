/** 3-segment progress bar (green = active/complete) — sign-in flow, PDF p.13. */
export function StepProgress({ step, total = 3 }: { step: number; total?: number }) {
  return (
    <div className="flex gap-1.5" aria-label={`Step ${step} of ${total}`}>
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={[
            'h-1 w-10 rounded-pill',
            i < step ? 'bg-green' : 'bg-hairline',
          ].join(' ')}
        />
      ))}
    </div>
  );
}
