// The search queue status doesn't echo the ticket, so the desk remembers what it
// queued (per browser) to recap it while searching.
export interface QueuedTicket {
  speed: string | null;
  entry_cents: number;
  rating: number | null;
  at: number;
}

const TTL_MS = 11 * 60 * 1000; // a little past the server's 10 min ticket TTL
const key = (userId: string | undefined) => `mm.h2h.ticket.${userId ?? 'anon'}`;

export function rememberTicket(userId: string | undefined, ticket: QueuedTicket) {
  try {
    window.localStorage.setItem(key(userId), JSON.stringify(ticket));
  } catch {
    /* recap is optional */
  }
}

export function recallTicket(
  userId: string | undefined,
  now: number = Date.now(),
): QueuedTicket | null {
  try {
    const t = JSON.parse(
      window.localStorage.getItem(key(userId)) ?? 'null',
    ) as QueuedTicket | null;
    return t && typeof t.entry_cents === 'number' && now - t.at < TTL_MS ? t : null;
  } catch {
    return null;
  }
}
