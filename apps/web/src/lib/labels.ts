// Friendly labels for the market/metric identifiers the API embeds in free-text
// it hands the client — most visibly the ledger `memo` ("chess_moves easy pool
// entry"). Mirrors METRIC_LABELS in the API's constants.py. Keep in sync when a
// metric/market is added.
const ID_LABELS: Record<string, string> = {
  // Metric ids (pool/tournament memos: "{metric} {difficulty} pool entry").
  chess_accuracy: 'Chess accuracy',
  chess_moves: 'Moves to win',
  chess_win_streak: 'Longest win streak',
  chess_wins: 'Total wins',
  chess_fastest_win: 'Fastest win',
  win_h2h: 'Head to head',
};

/** Title-case a bare snake_case id so an unmapped identifier never shows raw. */
function desnake(id: string): string {
  const spaced = id.replace(/_/g, ' ');
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * Replace snake_case market/metric ids inside a server string with friendly
 * labels, leaving the surrounding words untouched. Unmapped ids are de-snaked
 * so a raw identifier (underscores) never reaches a user. Consumer surfaces
 * only — admin tools intentionally keep raw ids.
 */
export function humanizeIds(text: string): string {
  return text.replace(
    /\b[a-z0-9]+(?:_[a-z0-9]+)+\b/g,
    (id) => ID_LABELS[id] ?? desnake(id),
  );
}
