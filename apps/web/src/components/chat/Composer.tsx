import { useEffect, useRef, useState, type FC } from 'react';

import { useSendMessage } from '../../hooks/useChat';
import { track } from '../../lib/telemetry';
import { PlusIcon, SendIcon, SwordsIcon, TrophyIcon, UsersIcon } from './icons';

export type InviteChoice = 'pool' | 'tournament' | 'h2h';

const INVITE_OPTIONS: {
  key: InviteChoice;
  label: string;
  hint: string;
  Icon: FC<{ className?: string }>;
}[] = [
  { key: 'pool', label: 'Solo pool', hint: 'Same bar, shared pot', Icon: UsersIcon },
  {
    key: 'tournament',
    label: 'Tournament',
    hint: 'Best matches, top split',
    Icon: TrophyIcon,
  },
  { key: 'h2h', label: 'Head-to-head', hint: 'Straight duel', Icon: SwordsIcon },
];

/**
 * The typing bar. The invite button sits right next to it (design ask): it opens
 * the three things you can invite a friend to, which is also the shortcut into
 * the Solo Pools / Tournament tabs.
 */
export function Composer({
  conversationId,
  disabled = false,
  canInvite,
  onPickInvite,
}: {
  conversationId: string;
  disabled?: boolean;
  /** Support threads take messages but not invites. */
  canInvite: boolean;
  onPickInvite: (choice: InviteChoice) => void;
}) {
  const [text, setText] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const send = useSendMessage();
  const menuRef = useRef<HTMLDivElement>(null);

  // Reset the draft when switching threads — a half-typed line shouldn't follow
  // you into someone else's conversation.
  useEffect(() => {
    setText('');
    setMenuOpen(false);
  }, [conversationId]);

  useEffect(() => {
    if (!menuOpen) return;
    function onDocClick(e: MouseEvent) {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [menuOpen]);

  async function submit() {
    const body = text.trim();
    if (!body || send.isPending) return;
    setText('');
    try {
      await send.mutateAsync({ conversationId, body });
      track('chat_message_sent');
    } catch {
      setText(body); // put the draft back rather than losing it
    }
  }

  return (
    <div className="border-t border-hairline bg-panel/60 px-4 py-4">
      {send.error && (
        <p className="mb-2 px-1 text-[13px] text-red">
          {(send.error as Error).message}
        </p>
      )}
      <div className="flex items-end gap-2.5">
        {canInvite && (
          <div className="relative" ref={menuRef}>
            {menuOpen && (
              <div
                role="menu"
                data-testid="invite-menu"
                className="absolute bottom-14 left-0 z-20 w-64 overflow-hidden rounded-2xl border border-hairline bg-panel-raised shadow-[0_20px_50px_-20px_rgba(0,0,0,0.9)]"
              >
                <p className="label-mono border-b border-hairline px-4 pb-2 pt-3">
                  Invite to
                </p>
                {INVITE_OPTIONS.map((opt) => (
                  <button
                    key={opt.key}
                    role="menuitem"
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      onPickInvite(opt.key);
                    }}
                    className="group flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-panel"
                  >
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-hairline text-green transition group-hover:border-green/50">
                      <opt.Icon className="h-4 w-4" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-[15px] font-semibold text-text">
                        {opt.label}
                      </span>
                      <span className="block text-xs text-text-secondary">
                        {opt.hint}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            )}
            <button
              type="button"
              aria-label="Send an invite"
              aria-expanded={menuOpen}
              disabled={disabled}
              onClick={() => setMenuOpen((v) => !v)}
              className={[
                'grid h-12 w-12 shrink-0 place-items-center rounded-full border transition',
                menuOpen
                  ? 'rotate-45 border-green bg-green text-black'
                  : 'border-hairline text-text-secondary hover:border-green hover:text-green',
              ].join(' ')}
            >
              <PlusIcon className="h-5 w-5" />
            </button>
          </div>
        )}

        <textarea
          rows={1}
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void submit();
            }
          }}
          placeholder="Write a message…"
          aria-label="Message"
          className="no-scrollbar max-h-40 min-h-[3rem] w-full flex-1 resize-none rounded-2xl border border-hairline bg-bg px-4 py-3 text-[15px] leading-relaxed text-text transition placeholder:text-text-tertiary focus:border-green/60 focus:shadow-[0_0_0_3px_rgba(198,244,64,0.08)] focus:outline-none"
        />

        <button
          type="button"
          aria-label="Send"
          disabled={disabled || !text.trim() || send.isPending}
          onClick={() => void submit()}
          className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-green text-black transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30 disabled:shadow-none [&:not(:disabled)]:shadow-[0_8px_24px_-12px_var(--green)]"
        >
          <SendIcon className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}
