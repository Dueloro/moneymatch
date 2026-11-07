import type { ReactNode } from 'react';

import { useHowItWorksIntro } from '../hooks/useHowItWorksIntro';
import { ModeSwitcher } from './ModeSwitcher';
import { HowItWorks, HowItWorksNote } from './ui/Disclosure';

/** Mode switcher, the "How it works" trigger, and a once-per-user inline intro. */
export function PlayHeader({ id, how }: { id: string; how: ReactNode }) {
  const [intro, dismiss] = useHowItWorksIntro();

  return (
    <div className="mb-6 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <ModeSwitcher />
        {!intro && (
          <div className="ml-auto">
            <HowItWorks id={id}>{how}</HowItWorks>
          </div>
        )}
      </div>
      {intro && <HowItWorksNote onDismiss={dismiss}>{how}</HowItWorksNote>}
    </div>
  );
}
