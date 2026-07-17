// Shared types used by both the Electron main process and the renderer.
// Keep in sync with electron/detector/types.ts (same shape, separate declaration
// because the renderer cannot import from the electron/ folder).

export interface GameTarget {
  process: string;
  title: string;
  bounds: { x: number; y: number; width: number; height: number };
  displayId: number;
}

export interface ContractContent {
  game: string;
  format: string;
  objective: string;
  stake: number;
  line: number;
  payout: number;
  fairLine: number;
  houseEdgePct: number;
  windowEndsAt: number;
  balance: number;
}
