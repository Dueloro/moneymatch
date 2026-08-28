import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrictMode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { GameSelectOverlay } from './GameSelectOverlay';

/** Find a tile toggle by its accessible name (label starts with the game name). */
function tile(name: RegExp) {
  return screen.getByRole('button', { name });
}

const cont = () => screen.getByRole('button', { name: 'Continue' });

describe('GameSelectOverlay', () => {
  describe('interactivity (which tiles respond)', () => {
    it('production: Chess, CS2 and PUBG are all selectable; only Dota is locked', () => {
      render(<GameSelectOverlay context="production" onConfirm={vi.fn()} />);

      for (const re of [/^Chess,/, /^Counter-Strike 2,/, /^PUBG,/]) {
        const t = tile(re);
        expect(t).not.toBeDisabled();
        expect(t).not.toHaveAttribute('aria-disabled');
      }
      const dota = tile(/^Dota 2,/);
      expect(dota).toBeDisabled();
      expect(dota).toHaveAttribute('aria-disabled', 'true');
    });

    it('Chess is no longer forced-on — it can be deselected like any tile', async () => {
      const user = userEvent.setup();
      render(<GameSelectOverlay context="demo" onConfirm={vi.fn()} />);
      const chess = tile(/^Chess,/);
      expect(chess).toHaveAttribute('aria-pressed', 'true'); // default-checked
      await user.click(chess);
      expect(tile(/^Chess,/)).toHaveAttribute('aria-pressed', 'false');
    });

    it('production: CS2 and PUBG toggle on and off (no longer locked)', async () => {
      const user = userEvent.setup();
      render(<GameSelectOverlay context="production" onConfirm={vi.fn()} />);
      for (const re of [/^Counter-Strike 2,/, /^PUBG,/]) {
        await user.click(tile(re));
        expect(tile(re)).toHaveAttribute('aria-pressed', 'true');
        await user.click(tile(re));
        expect(tile(re)).toHaveAttribute('aria-pressed', 'false');
      }
    });

    it('production: Dota is non-interactive — clicking does not select it', async () => {
      const user = userEvent.setup();
      render(<GameSelectOverlay context="production" onConfirm={vi.fn()} />);
      const dota = tile(/^Dota 2,/);
      await user.click(dota);
      expect(dota).toHaveAttribute('aria-pressed', 'false');
    });

    it('demo: Dota 2 stays selectable despite its SOON/grayscale look', async () => {
      const user = userEvent.setup();
      render(<GameSelectOverlay context="demo" onConfirm={vi.fn()} />);
      const dota = tile(/^Dota 2,/);
      expect(dota).not.toBeDisabled();
      await user.click(dota);
      expect(tile(/^Dota 2,/)).toHaveAttribute('aria-pressed', 'true');
    });

    it('toggling works under StrictMode (pure updater, no double-toggle)', async () => {
      const user = userEvent.setup();
      render(
        <StrictMode>
          <GameSelectOverlay context="production" onConfirm={vi.fn()} />
        </StrictMode>,
      );
      const cs2 = tile(/^Counter-Strike 2,/);
      await user.click(cs2);
      expect(tile(/^Counter-Strike 2,/)).toHaveAttribute('aria-pressed', 'true');
    });
  });

  describe('validation on Continue (two distinct states)', () => {
    it('production: selecting a BETA game blocks Continue with an invite-only-beta error', async () => {
      const user = userEvent.setup();
      const onConfirm = vi.fn();
      render(<GameSelectOverlay context="production" onConfirm={onConfirm} />);

      await user.click(tile(/^Counter-Strike 2,/));
      expect(screen.getByRole('alert')).toHaveTextContent(
        'CS2 is only available in an invite-only beta.',
      );
      expect(cont()).toBeDisabled();
      await user.click(cont());
      expect(onConfirm).not.toHaveBeenCalled();
    });

    it('production: both BETA games selected name both in the error', async () => {
      const user = userEvent.setup();
      render(<GameSelectOverlay context="production" onConfirm={vi.fn()} />);
      await user.click(tile(/^Counter-Strike 2,/));
      await user.click(tile(/^PUBG,/));
      expect(screen.getByRole('alert')).toHaveTextContent(
        'CS2 and PUBG are only available in an invite-only beta.',
      );
    });

    it('production: deselecting the BETA game clears the error and re-enables Continue', async () => {
      const user = userEvent.setup();
      render(<GameSelectOverlay context="production" onConfirm={vi.fn()} />);
      await user.click(tile(/^Counter-Strike 2,/)); // Chess + CS2 selected
      expect(cont()).toBeDisabled();
      await user.click(tile(/^Counter-Strike 2,/)); // back to Chess only
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(cont()).toBeEnabled();
    });

    it('empty selection is a distinct error from the beta gate', async () => {
      const user = userEvent.setup();
      render(<GameSelectOverlay context="production" onConfirm={vi.fn()} />);
      await user.click(tile(/^Chess,/)); // deselect the only selectable non-beta
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Pick at least one game to continue.',
      );
      expect(cont()).toBeDisabled();
    });

    it('production: Chess-only is valid — Continue is enabled with no error', () => {
      render(<GameSelectOverlay context="production" onConfirm={vi.fn()} />);
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(cont()).toBeEnabled();
    });

    it('demo: BETA games are NOT gated — Continue submits the chosen set', async () => {
      const user = userEvent.setup();
      const onConfirm = vi.fn();
      render(<GameSelectOverlay context="demo" onConfirm={onConfirm} />);
      await user.click(tile(/^Counter-Strike 2,/));
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      await user.click(cont());
      expect(onConfirm).toHaveBeenCalledTimes(1);
      const picked = onConfirm.mock.calls[0][0] as string[];
      expect(picked).toContain('chess.lichess');
      expect(picked).toContain('cs2.steam');
    });
  });

  describe('labels and seeding', () => {
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
      expect(tile(/^Counter-Strike 2,/)).toHaveAttribute('aria-pressed', 'true');
      await user.keyboard('{Enter}');
      expect(tile(/^Counter-Strike 2,/)).toHaveAttribute('aria-pressed', 'false');
    });

    it('seeds a selectable game from initialSelected but drops a locked one', () => {
      // CS2 is now selectable in production, so a seeded CS2 selection is KEPT
      // (and will gate Continue). Dota is still locked in production, so a seeded
      // Dota selection is dropped.
      render(
        <GameSelectOverlay
          context="production"
          initialSelected={['cs2.steam', 'dota2.opendota']}
          onConfirm={vi.fn()}
        />,
      );
      expect(tile(/^Counter-Strike 2,/)).toHaveAttribute('aria-pressed', 'true');
      expect(tile(/^Dota 2,/)).toHaveAttribute('aria-pressed', 'false');
    });
  });
});
