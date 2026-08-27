import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { GameSelectOverlay } from './GameSelectOverlay';

/** Find a tile toggle by its accessible name (label starts with the game name). */
function tile(name: RegExp) {
  return screen.getByRole('button', { name });
}

describe('GameSelectOverlay', () => {
  it('production: only Chess is selectable; CS2/PUBG/Dota are disabled', () => {
    render(<GameSelectOverlay context="production" onConfirm={vi.fn()} />);

    // Chess is pre-selected and required.
    expect(tile(/^Chess,/)).toHaveAttribute('aria-pressed', 'true');

    for (const re of [/^Counter-Strike 2,/, /^PUBG,/, /^Dota 2,/]) {
      const t = tile(re);
      expect(t).toBeDisabled();
      expect(t).toHaveAttribute('aria-disabled', 'true');
    }
    // A minimum of one (Chess) is always met, so Continue is enabled.
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled();
  });

  it('production: clicking a locked tile does not select it', async () => {
    const user = userEvent.setup();
    render(<GameSelectOverlay context="production" onConfirm={vi.fn()} />);
    const cs2 = tile(/^Counter-Strike 2,/);
    await user.click(cs2);
    expect(cs2).toHaveAttribute('aria-pressed', 'false');
  });

  it('Chess is required — it cannot be deselected', async () => {
    const user = userEvent.setup();
    render(<GameSelectOverlay context="demo" onConfirm={vi.fn()} />);
    const chess = tile(/^Chess,/);
    expect(chess).toHaveAttribute('aria-pressed', 'true');
    await user.click(chess);
    expect(chess).toHaveAttribute('aria-pressed', 'true');
  });

  it('demo: CS2 and PUBG toggle on and off', async () => {
    const user = userEvent.setup();
    render(<GameSelectOverlay context="demo" onConfirm={vi.fn()} />);

    const cs2 = tile(/^Counter-Strike 2,/);
    expect(cs2).toBeEnabled();
    await user.click(cs2);
    expect(cs2).toHaveAttribute('aria-pressed', 'true');
    await user.click(cs2);
    expect(cs2).toHaveAttribute('aria-pressed', 'false');
  });

  it('demo: Dota 2 is selectable despite its SOON/grayscale look', async () => {
    const user = userEvent.setup();
    render(<GameSelectOverlay context="demo" onConfirm={vi.fn()} />);
    const dota = tile(/^Dota 2,/);
    expect(dota).not.toBeDisabled();
    expect(dota).toHaveAttribute('aria-pressed', 'false');
    await user.click(dota);
    expect(dota).toHaveAttribute('aria-pressed', 'true');
  });

  it('labels include badge state', () => {
    render(<GameSelectOverlay context="demo" onConfirm={vi.fn()} />);
    expect(tile(/Counter-Strike 2, \(BETA\)/)).toBeInTheDocument();
    expect(tile(/Dota 2, \(SOON\)/)).toBeInTheDocument();
  });

  it('is fully keyboard operable', async () => {
    const user = userEvent.setup();
    render(<GameSelectOverlay context="demo" onConfirm={vi.fn()} />);
    const cs2 = tile(/^Counter-Strike 2,/);
    cs2.focus();
    expect(cs2).toHaveFocus();
    await user.keyboard(' '); // Space toggles a button
    expect(cs2).toHaveAttribute('aria-pressed', 'true');
    await user.keyboard('{Enter}');
    expect(cs2).toHaveAttribute('aria-pressed', 'false');
  });

  it('confirms with the selected set (Chess always included)', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<GameSelectOverlay context="demo" onConfirm={onConfirm} />);
    await user.click(tile(/^PUBG,/));
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    const picked = onConfirm.mock.calls[0][0] as string[];
    expect(picked).toContain('chess.lichess');
    expect(picked).toContain('pubg.steam');
  });

  it('seeds from initialSelected but drops games locked in the context', () => {
    // CS2 is locked in production, so a pre-existing CS2 selection is dropped.
    render(
      <GameSelectOverlay
        context="production"
        initialSelected={['cs2.steam']}
        onConfirm={vi.fn()}
      />,
    );
    expect(tile(/^Counter-Strike 2,/)).toHaveAttribute('aria-pressed', 'false');
  });
});
