// Display-only head-to-head match ideas per game, used for the blurred "preview"
// state in the Lobby (a game you haven't linked / that's coming soon). These are
// illustrative — real matches are matched and built once a game links.

export interface SampleContract {
  title: string;
  detail: string;
  entry: number; // teaser entry
  prize: number; // teaser prize (pot minus rake) for the line
}

export const SAMPLE_CONTRACTS: Record<string, SampleContract[]> = {
  'chess.lichess': [
    { title: 'Win the blitz match', detail: 'Beat a player in your rating band, head-to-head.', entry: 5, prize: 9.2 },
    { title: 'Win in under 30 moves', detail: 'Take the match inside 30 moves for a bigger pot.', entry: 5, prize: 8.8 },
    { title: 'Win the rapid match', detail: 'Single rapid game, winner takes the pot.', entry: 10, prize: 18.4 },
    { title: 'High-stakes bullet', detail: 'One bullet game, even bracket.', entry: 25, prize: 46 },
  ],
  'cs2.steam': [
    { title: 'Win the 1v1', detail: 'Aim-map duel against a bracketed opponent.', entry: 5, prize: 9 },
    { title: 'Best of three', detail: 'Take 2 of 3 rounds to win the pot.', entry: 10, prize: 18 },
    { title: 'Top-frag duel', detail: 'Most kills in a shared match wins.', entry: 5, prize: 8.8 },
    { title: 'High-stakes 1v1', detail: 'One round, winner takes all (minus rake).', entry: 25, prize: 45 },
  ],
  'clashroyale.supercell': [
    { title: 'Win the ladder duel', detail: 'Head-to-head match in your trophy band.', entry: 5, prize: 9 },
    { title: 'Three-crown challenge', detail: 'Win by three crowns for a bigger pot.', entry: 5, prize: 8.5 },
    { title: 'Best of three', detail: 'First to two match wins takes the pot.', entry: 10, prize: 18 },
    { title: 'High-stakes duel', detail: 'One match, even bracket.', entry: 25, prize: 45 },
  ],
  'rocketleague.psyonix': [
    { title: 'Win the 1v1', detail: 'Ranked duel against a bracketed opponent.', entry: 5, prize: 9 },
    { title: 'First to 3 goals', detail: 'Race to three goals wins the pot.', entry: 5, prize: 8.8 },
    { title: 'Best of three', detail: 'Take 2 of 3 games to win.', entry: 10, prize: 18 },
    { title: 'High-stakes 1v1', detail: 'One game, winner takes the pot.', entry: 25, prize: 45 },
  ],
};
