const ID_LABELS: Record<string, string> = {
  chess_accuracy: 'Chess accuracy',
  chess_moves: 'Moves to win',
  chess_win_streak: 'Longest win streak',
  chess_wins: 'Total wins',
  chess_fastest_win: 'Fastest win',
  win_h2h: 'Head to head',
};

function desnake(id: string): string {
  const spaced = id.replace(/_/g, ' ');
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * Replace snake_case market/metric ids inside a server string with friendly
 * labels, leaving the surrounding words untouched.
 */
export function humanizeIds(text: string): string {
  return text.replace(
    /\b[a-z0-9]+(?:_[a-z0-9]+)+\b/g,
    (id) => ID_LABELS[id] ?? desnake(id),
  );
}

// Every user-ledger entry_type the API can write (models/wallet.py
// ck_ledger_entry_type), refined by ref_type where it reads better.
const LEDGER_BY_REF: Record<string, Record<string, string>> = {
  escrow_hold: {
    match: 'Match stake',
    solo_pool: 'Pool stake',
    tournament: 'Tournament stake',
  },
  payout: {
    match: 'Match winnings',
    solo_pool: 'Pool winnings',
    tournament: 'Tournament winnings',
  },
};

const LEDGER_LABELS: Record<string, string> = {
  demo_deposit: 'Points added',
  demo_withdrawal: 'Points removed',
  escrow_hold: 'Stake',
  escrow_release: 'Stake to pot',
  payout: 'Winnings',
  refund: 'Stake refunded',
  rake: 'Platform fee',
  adjustment: 'Adjustment',
};

export const SIGNUP_GRANT_MEMO = 'signup grant';

export function ledgerLabel(entry: {
  entry_type: string;
  ref_type: string;
  memo: string | null;
}): string {
  if (entry.entry_type === 'demo_deposit' && entry.memo === SIGNUP_GRANT_MEMO) {
    return 'Welcome points';
  }
  return (
    LEDGER_BY_REF[entry.entry_type]?.[entry.ref_type] ??
    LEDGER_LABELS[entry.entry_type] ??
    desnake(entry.entry_type)
  );
}
