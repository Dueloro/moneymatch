import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useSendMessage } from '../../hooks/useChat';
import { CHESS } from '../../lib/games';
import { Dialog } from '../ui/Dialog';
import { PillButton } from '../ui/PillButton';
import { PresetSelector } from '../ui/PresetSelector';

const ENTRY_PRESETS = [500, 1000, 2500];
const DIFFICULTIES = ['easy', 'medium', 'hard'];

const COPY = {
  pool: {
    title: 'Invite to a solo pool',
    blurb:
      'Drops an invite card in this chat. Rooms are joined on the Solo Pools tab. Open it to pick the exact room.',
    tab: 'Solo Pools',
    path: '/pools',
  },
  tournament: {
    title: 'Invite to a tournament',
    blurb:
      'Drops an invite card in this chat. Fields are joined on the Tournament tab. Open it to pick the exact field.',
    tab: 'Tournament',
    path: '/tournament',
  },
} as const;

export function InviteSheet({
  conversationId,
  kind,
  peerName,
  onClose,
}: {
  conversationId: string;
  kind: 'pool' | 'tournament';
  peerName: string;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const send = useSendMessage();
  const copy = COPY[kind];

  const [entryCents, setEntryCents] = useState<number | null>(ENTRY_PRESETS[1]);
  const [difficulty, setDifficulty] = useState<string>('medium');

  async function sendInvite() {
    if (!entryCents) return;
    await send.mutateAsync({
      conversationId,
      invite: {
        invite_kind: kind,
        game: CHESS,
        entry_preset_cents: entryCents,
        difficulty: kind === 'pool' ? difficulty : null,
      },
    });
    onClose();
  }

  return (
    <Dialog
      title={copy.title}
      onClose={onClose}
      testId="invite-sheet"
      width="md:max-w-lg"
    >
      <div className="overflow-y-auto px-5 pb-5 pt-2 md:px-6 md:pb-6">
        <p className="mb-6 text-xs leading-relaxed text-text-secondary">{copy.blurb}</p>

        {kind === 'pool' && (
          <>
            <p className="label-neutral mb-2.5">Difficulty</p>
            <div className="mb-6 flex flex-wrap gap-2">
              {DIFFICULTIES.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDifficulty(d)}
                  className={[
                    'rounded-pill border px-4 py-1.5 text-xs font-semibold capitalize transition',
                    d === difficulty
                      ? 'is-selected text-text'
                      : 'border-hairline text-text-secondary hover:text-text',
                  ].join(' ')}
                >
                  {d}
                </button>
              ))}
            </div>
          </>
        )}

        <p className="label-money mb-2.5">Entry</p>
        <PresetSelector
          presetsCents={ENTRY_PRESETS}
          selectedCents={entryCents}
          onSelect={setEntryCents}
        />

        {send.error && (
          <p className="mt-3 text-xs text-red">{(send.error as Error).message}</p>
        )}

        <div className="mt-6 flex flex-wrap items-center gap-2">
          <PillButton disabled={!entryCents || send.isPending} onClick={sendInvite}>
            {send.isPending ? 'Sending…' : `Send to ${peerName}`}
          </PillButton>
          <PillButton variant="outline" onClick={() => navigate(copy.path)}>
            Open {copy.tab} ↗
          </PillButton>
        </div>
      </div>
    </Dialog>
  );
}
