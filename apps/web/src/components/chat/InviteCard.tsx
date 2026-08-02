import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

import { useRespondInvite, type ChatMessage } from '../../hooks/useChat';
import { formatCurrency } from '../../lib/format';
import { gameMeta } from '../../lib/games';
import { PillButton } from '../ui/PillButton';
import { SwordsIcon, TrophyIcon, UsersIcon } from './icons';

const KIND_META = {
  pool: { label: 'Solo pool invite', Icon: UsersIcon, path: '/pools' },
  tournament: { label: 'Tournament invite', Icon: TrophyIcon, path: '/tournament' },
  h2h: { label: 'Head-to-head challenge', Icon: SwordsIcon, path: '/play' },
} as const;

/** Small metadata pill inside an invite card (game, entry, friendly). */
function Chip({
  children,
  highlight = false,
}: {
  children: ReactNode;
  highlight?: boolean;
}) {
  return (
    <span
      className={[
        'rounded-pill border px-2.5 py-1 text-[11px] font-medium',
        highlight
          ? 'border-green/40 bg-green/10 text-green'
          : 'border-hairline text-text-secondary',
      ].join(' ')}
    >
      {children}
    </span>
  );
}

const STATUS_STYLE: Record<string, string> = {
  accepted: 'border-green/50 text-green',
  declined: 'border-hairline text-text-tertiary',
  expired: 'border-hairline text-text-tertiary',
};

/**
 * An invite rendered inside the thread (design: the invite lands where you talk,
 * not only in the notification feed). A head-to-head card wraps a real challenge
 * — accepting forms the PENDING match and jumps to it. Pool / tournament cards
 * open the tab where the room is actually joined.
 */
export function InviteCard({ message }: { message: ChatMessage }) {
  const navigate = useNavigate();
  const respond = useRespondInvite();
  const p = message.payload;
  const kind = (p.invite_kind ?? 'pool') as keyof typeof KIND_META;
  const meta = KIND_META[kind] ?? KIND_META.pool;
  const status = p.status ?? 'pending';
  const accent = p.game ? gameMeta(p.game).accent : 'var(--green)';
  const pending = status === 'pending';

  async function onRespond(action: 'accept' | 'decline') {
    const res = await respond.mutateAsync({
      conversationId: message.conversation_id,
      messageId: message.id,
      action,
    });
    if (action !== 'accept') return;
    if (res.match_id) {
      navigate(`/play?match=${res.match_id}`);
    } else if (res.redirect_path) {
      navigate(res.redirect_path);
    }
  }

  return (
    <div
      data-testid="invite-card"
      className="w-full max-w-md overflow-hidden rounded-2xl border border-hairline bg-panel-raised shadow-[0_16px_40px_-24px_rgba(0,0,0,0.9)]"
      style={{
        // A faint wash of the game's accent, so a CS2 card reads differently
        // from a PUBG one at a glance.
        backgroundImage: `linear-gradient(180deg, color-mix(in srgb, ${accent} 8%, transparent), transparent 60%)`,
      }}
    >
      <div className="h-1 w-full" style={{ background: accent }} />
      <div className="p-4">
        <div className="flex items-center gap-2 text-text-secondary">
          <span
            className="grid h-7 w-7 shrink-0 place-items-center rounded-full border"
            style={{
              color: accent,
              borderColor: `color-mix(in srgb, ${accent} 45%, transparent)`,
            }}
          >
            <meta.Icon className="h-4 w-4" />
          </span>
          <span className="label-mono !text-[10px]">{meta.label}</span>
          {!pending && (
            <span
              className={[
                'ml-auto rounded-pill border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                STATUS_STYLE[status] ?? 'border-hairline text-text-tertiary',
              ].join(' ')}
            >
              {status}
            </span>
          )}
        </div>

        <p className="mt-3 text-base font-bold leading-snug text-text">
          {p.title ?? 'Invite'}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <Chip>{p.game ? gameMeta(p.game).name : 'Game'}</Chip>
          {p.entry_cents != null && (
            <Chip highlight>{formatCurrency(p.entry_cents)} entry</Chip>
          )}
          {p.friendly && <Chip>friendly · no rake</Chip>}
        </div>

        {respond.error && (
          <p className="mt-2.5 text-xs text-red">{(respond.error as Error).message}</p>
        )}

        <div className="mt-4 flex items-center gap-2">
          {pending && message.mine && (
            <p className="text-xs text-text-tertiary">Waiting for a reply…</p>
          )}
          {pending && !message.mine && (
            <>
              <PillButton
                className="!px-5 !py-2"
                disabled={respond.isPending}
                onClick={() => onRespond('accept')}
              >
                {kind === 'h2h' ? 'Accept' : 'Join'}
              </PillButton>
              <PillButton
                variant="text"
                className="!px-3 !py-2"
                disabled={respond.isPending}
                onClick={() => onRespond('decline')}
              >
                Decline
              </PillButton>
            </>
          )}
          {!pending && status === 'accepted' && (
            <PillButton
              variant="outline"
              className="!px-5 !py-2"
              onClick={() =>
                navigate(p.match_id ? `/play?match=${p.match_id}` : meta.path)
              }
            >
              Open
            </PillButton>
          )}
        </div>
      </div>
    </div>
  );
}
