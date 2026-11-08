import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useSendMessage } from '../../hooks/useChat';
import { CHESS } from '../../lib/games';
import { PointsFigure } from '../ui/AmountText';
import { Dialog } from '../ui/Dialog';
import { PillButton } from '../ui/PillButton';
import { StakeChoice } from '../ui/MatchChoices';
import { Segmented } from '../ui/Segmented';

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

  const [entryCents, setEntryCents] = useState<number>(ENTRY_PRESETS[1]);
  const [difficulty, setDifficulty] = useState<string>('medium');

  async function sendInvite() {
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
      <div className="flex flex-col gap-5 overflow-y-auto px-5 py-4 md:px-6">
        <p className="text-xs leading-relaxed text-text-secondary">{copy.blurb}</p>

        {kind === 'pool' && (
          <div>
            <p className="label-neutral mb-2">Difficulty</p>
            <Segmented
              size="lg"
              fullWidth
              ariaLabel="Difficulty"
              options={DIFFICULTIES.map((d) => ({
                value: d,
                label: <span className="capitalize">{d}</span>,
              }))}
              value={difficulty}
              onChange={setDifficulty}
            />
          </div>
        )}

        <StakeChoice
          presets={ENTRY_PRESETS}
          value={entryCents}
          onChange={setEntryCents}
        />

        {send.error && (
          <p className="text-xs text-red">{(send.error as Error).message}</p>
        )}
      </div>

      <div className="flex flex-col gap-2 border-t border-hairline px-5 py-5 md:flex-row-reverse md:px-6">
        <PillButton
          size="lg"
          className="mm-glow md:flex-1"
          disabled={send.isPending}
          onClick={sendInvite}
        >
          {send.isPending ? (
            'Sending…'
          ) : (
            <>
              Send to {peerName} · <PointsFigure cents={entryCents} />
            </>
          )}
        </PillButton>
        <PillButton
          size="lg"
          variant="outline"
          className="md:flex-1"
          onClick={() => navigate(copy.path)}
        >
          Open {copy.tab} ↗
        </PillButton>
      </div>
    </Dialog>
  );
}
