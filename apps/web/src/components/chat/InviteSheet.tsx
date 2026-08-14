import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useGameSelection } from '../../hooks/useGameSelection';
import { useSendMessage } from '../../hooks/useChat';
import { gameMeta } from '../../lib/games';
import { PillButton } from '../ui/PillButton';
import { PresetSelector } from '../ui/PresetSelector';

// The server validates entry against its own presets (`ENTRY_PRESETS_CENTS`);
// these are the same three amounts every wager surface offers.
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

/**
 * Compose a pool / tournament invite from inside a thread: pick a game and an
 * entry preset, and the card lands in the conversation. "Open <tab>" is the
 * escape hatch to the surface where rooms are actually joined.
 */
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
  const { games } = useGameSelection();
  const send = useSendMessage();
  const copy = COPY[kind];

  const gameIds = games.length > 0 ? games.map((g) => g.game) : ['cs2.steam'];
  const [game, setGame] = useState(gameIds[0]);
  const [entryCents, setEntryCents] = useState<number | null>(ENTRY_PRESETS[1]);
  const [difficulty, setDifficulty] = useState<string>('medium');

  async function sendInvite() {
    if (!entryCents) return;
    await send.mutateAsync({
      conversationId,
      invite: {
        invite_kind: kind,
        game,
        entry_preset_cents: entryCents,
        difficulty: kind === 'pool' ? difficulty : null,
      },
    });
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={copy.title}
    >
      <div
        className="w-full max-w-lg rounded-card border border-hairline bg-panel p-7 shadow-overlay"
        data-testid="invite-sheet"
      >
        <div className="mb-1 flex items-start justify-between gap-4">
          <h3 className="text-xl font-bold text-text">{copy.title}</h3>
          <PillButton variant="text" className="!px-2" onClick={onClose}>
            Close
          </PillButton>
        </div>
        <p className="mb-6 text-xs leading-relaxed text-text-secondary">{copy.blurb}</p>

        <p className="label-money mb-2.5">Game</p>
        <div className="mb-6 flex flex-wrap gap-2">
          {gameIds.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setGame(id)}
              className={[
                'rounded-pill px-4 py-1.5 text-xs font-semibold transition',
                id === game
                  ? 'bg-text text-black'
                  : 'border border-hairline text-text-secondary hover:text-text',
              ].join(' ')}
            >
              {gameMeta(id).short}
            </button>
          ))}
        </div>

        {kind === 'pool' && (
          <>
            <p className="label-money mb-2.5">Difficulty</p>
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
    </div>
  );
}
