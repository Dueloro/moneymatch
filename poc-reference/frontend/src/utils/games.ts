import type { LucideIcon } from 'lucide-react';
import { Castle, Crosshair, Rocket, Swords, Wand2 } from 'lucide-react';

// The titles Money Match offers contracts on. `live` games can be linked and
// built today; the rest are teased as coming soon. Single source of truth for
// the Link Accounts tab, the Catalog game tabs, and the Profile.

export interface GameProvider {
  id: string;
  name: string;
  live: boolean;
}

export interface GameMeta {
  id: string; // adapter id (mirrors api/_lib/adapters)
  name: string;
  tag: string;
  color: string; // accent
  gradient: string; // logo-tile background
  icon: LucideIcon;
  live: boolean;
  /** Where you can link this game from (chess: Lichess live, Chess.com soon). */
  providers: GameProvider[];
  /** Optional placeholder/hint for the link input (e.g. how to find your id). */
  linkHint?: string;
}

export const GAMES: GameMeta[] = [
  {
    id: 'chess.lichess',
    name: 'Chess',
    tag: 'Strategy',
    color: '#9b8cff',
    gradient: 'linear-gradient(135deg, #7c6cf0, #b6a8ff)',
    icon: Castle,
    live: true,
    providers: [
      { id: 'lichess', name: 'Lichess', live: true },
      { id: 'chesscom', name: 'Chess.com', live: false },
    ],
  },
  {
    id: 'cs2.faceit',
    name: 'Counter-Strike 2',
    tag: 'FPS',
    color: '#e0a13a',
    gradient: 'linear-gradient(135deg, #d98a2b, #f0c468)',
    icon: Crosshair,
    live: true,
    providers: [{ id: 'faceit', name: 'FACEIT', live: true }],
  },
  {
    id: 'dota2.opendota',
    name: 'Dota 2',
    tag: 'MOBA',
    color: '#c0392b',
    gradient: 'linear-gradient(135deg, #b03a2e, #e8654f)',
    icon: Wand2,
    live: true,
    providers: [{ id: 'opendota', name: 'OpenDota', live: true }],
    linkHint: 'Steam32 account ID (e.g. 70388657)',
  },
  {
    id: 'clashroyale.supercell',
    name: 'Clash Royale',
    tag: 'Strategy',
    color: '#1bb8c9',
    gradient: 'linear-gradient(135deg, #14a6c0, #3ad6dd)',
    icon: Swords,
    live: false,
    providers: [{ id: 'supercell', name: 'Supercell ID', live: false }],
  },
  {
    id: 'rocketleague.psyonix',
    name: 'Rocket League',
    tag: 'Sports',
    color: '#3a7be0',
    gradient: 'linear-gradient(135deg, #2b67d9, #5e9bf0)',
    icon: Rocket,
    live: false,
    providers: [{ id: 'epic', name: 'Epic Games', live: false }],
  },
];

export const LIVE_GAMES = GAMES.filter((g) => g.live);
export const COMING_SOON_GAMES = GAMES.filter((g) => !g.live);

export const gameById = (id: string): GameMeta | undefined =>
  GAMES.find((g) => g.id === id);
