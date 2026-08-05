import type { ChatMessage } from '../../hooks/useChat';
import { Avatar } from './Avatar';
import { InviteCard } from './InviteCard';

function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });
}

/**
 * One line in the thread. Yours sits right and lime; theirs sits left on a
 * raised panel; a platform `system` line is a centered, quiet note. Invite
 * cards render as themselves rather than as a bubble.
 */
export function MessageBubble({
  message,
  showAvatar,
  peerName,
}: {
  message: ChatMessage;
  /** First message of a run from the same sender, so only then show the avatar. */
  showAvatar: boolean;
  peerName: string;
}) {
  if (message.kind === 'system' && message.sender_id === null) {
    return (
      <div className="my-1.5 flex justify-center">
        <p className="max-w-md rounded-pill border border-hairline bg-panel px-3.5 py-1.5 text-center text-xs text-text-tertiary">
          {message.body}
        </p>
      </div>
    );
  }

  const mine = message.mine;
  const name = mine ? 'You' : (message.sender_username ?? peerName);

  return (
    <div className={['flex gap-2.5', mine ? 'justify-end' : 'justify-start'].join(' ')}>
      {!mine &&
        (showAvatar ? (
          <Avatar name={name} size="sm" />
        ) : (
          <span className="w-10 shrink-0" aria-hidden />
        ))}

      <div
        className={[
          'flex min-w-0 max-w-[min(34rem,82%)] flex-col gap-1',
          mine ? 'items-end' : 'items-start',
        ].join(' ')}
      >
        {!mine && showAvatar && (
          <span className="px-1 text-micro font-semibold text-text-secondary">
            {name}
          </span>
        )}
        {message.kind === 'invite' ? (
          <InviteCard message={message} />
        ) : (
          <div
            className={[
              'whitespace-pre-wrap break-words px-4 py-2.5 text-sm leading-relaxed',
              mine
                ? 'rounded-card rounded-br-sm bg-action font-medium text-bg'
                : 'rounded-card rounded-bl-sm border border-hairline bg-panel-raised text-text',
            ].join(' ')}
          >
            {message.body}
          </div>
        )}
        <span className="px-1 text-micro text-text-tertiary">
          {clockTime(message.created_at)}
        </span>
      </div>
    </div>
  );
}
