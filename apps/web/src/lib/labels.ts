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
