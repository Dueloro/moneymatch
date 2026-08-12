import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { GameBadge } from './GameBadge';

describe('GameBadge', () => {
  it('names known games by their short label', () => {
    render(<GameBadge game="chess.lichess" />);
    expect(screen.getByText('Chess')).toBeInTheDocument();
  });

  it('labels CS2 and Dota distinctly', () => {
    const { rerender } = render(<GameBadge game="cs2.steam" />);
    expect(screen.getByText('CS2')).toBeInTheDocument();
    rerender(<GameBadge game="dota2.opendota" />);
    expect(screen.getByText('Dota 2')).toBeInTheDocument();
  });

  it('falls back to a passed-in name for an unknown game id', () => {
    render(<GameBadge game="valorant.riot" fallbackName="Valorant · ranked" />);
    expect(screen.getByText('Valorant')).toBeInTheDocument();
  });
});
