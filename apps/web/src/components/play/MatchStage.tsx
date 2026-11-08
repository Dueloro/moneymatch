import { lazy, Suspense, useEffect, useRef, useState } from 'react';

import { useCreateChallenge } from '../../hooks/useChallenges';
import { useCountUp } from '../../hooks/useCountUp';
import { formatClock, useLiveClocks } from '../../hooks/useLiveClocks';
import type { MatchLive, MatchPlayerView, MatchView } from '../../hooks/useMatchmaking';
import { useClaimSettlement } from '../../hooks/useSettlement';
import { formatPoints } from '../../lib/format';
import {
  formatDuration,
  lichessGameUrl,
  matchOutcome,
  resultLine,
  settleSeconds,
  terminationPhrase,
  type MatchOutcome,
} from '../../lib/matchResult';
import { clockFor, timeControlLabel, type SpeedClock } from '../../lib/timeControl';
import { toast } from '../../lib/toast';
import { AmountText } from '../ui/AmountText';
import { Card } from '../ui/Card';
import { PillButton } from '../ui/PillButton';
import { pillClassName } from '../ui/pillClass';
import { Skeleton } from '../ui/Skeleton';
import { QuietMark, WinMark } from './ResultMarks';

const ChessBoard = lazy(() => import('./board/ChessBoard'));

/** A result this fresh plays the settlement moment; older ones just show. */
const MOMENT_MS = 2 * 60 * 1000;
/** Before the first board arrives, assume the game is still being set up. */
const SETUP_MS = 3 * 60 * 1000;

type BoardState = 'waiting' | 'live' | 'finished' | 'unavailable';

function boardState(match: MatchView, settled: boolean): BoardState {
  const live = match.live;
  if (live?.status === 'finished') return 'finished';
  if (live?.status === 'live') return (live.san?.length ?? 0) > 0 ? 'live' : 'waiting';
  if (settled) return 'unavailable';
  if (live?.status === 'waiting') return 'waiting';
  const since = match.matched_at ? Date.now() - Date.parse(match.matched_at) : Infinity;
  return match.state === 'ACTIVE' && since < SETUP_MS ? 'waiting' : 'unavailable';
}

function liveClock(live: MatchLive | null | undefined): SpeedClock | null {
  return live?.clock
    ? {
        speed: '',
        limit_seconds: live.clock.limit,
        increment_seconds: live.clock.increment,
      }
    : null;
}

/**
 * Head to head from both confirms to the result: who's playing, the live board
 * and clocks, the game link, then the result card in the same frame.
 */
export function MatchStage({
  match,
  clocks,
  onPlayAgain,
}: {
  match: MatchView;
  clocks?: SpeedClock[];
  onPlayAgain: () => void;
}) {
  useClaimSettlement(match.id);
  const outcome = matchOutcome(match);
  const settled = outcome != null;
  const state = boardState(match, settled);
  const you = match.players.find((p) => p.is_you);
  const opp = match.players.find((p) => !p.is_you);
  const yourColor = match.live?.your_color ?? (you?.color as 'white' | 'black' | null);
  const tc = timeControlLabel(
    match.speed,
    clockFor(match.speed, clocks) ?? liveClock(match.live),
  );
  const gameUrl =
    match.your_play_url ?? lichessGameUrl(match.host_game_id, yourColor) ?? null;

  // Play the moment when the result lands while you're here, or just landed.
  const sawLive = useRef(!settled);
  const fresh =
    settled &&
    (sawLive.current ||
      (match.resolved_at != null &&
        Date.now() - Date.parse(match.resolved_at) < MOMENT_MS));

  const status = stageStatus(match, state, outcome);
  const hasBoard = state !== 'unavailable';

  return (
    <Card
      as="section"
      aria-label="Your match"
      className="overflow-hidden"
      data-testid="match-stage"
      data-state={outcome ?? state}
    >
      <header className="flex items-center justify-between gap-3 border-b border-hairline px-5 py-3 md:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <span
            aria-hidden
            className={`h-2 w-2 shrink-0 rounded-full ${
              status.live ? 'animate-pulse bg-live' : 'bg-text-tertiary'
            }`}
          />
          <span className="truncate text-sm font-semibold text-text">
            {status.word}
          </span>
        </div>
        {tc && (
          <span className="num shrink-0 rounded-pill border border-hairline px-2.5 py-0.5 text-micro text-text-secondary">
            {tc}
          </span>
        )}
      </header>

      <div
        className={
          hasBoard
            ? 'grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_17.5rem]'
            : 'grid grid-cols-1'
        }
      >
        {hasBoard && (
          <div className="order-2 px-4 py-4 md:order-1 md:px-6 md:py-5">
            <BoardColumn
              match={match}
              state={state}
              you={you}
              opp={opp}
              outcome={outcome}
            />
          </div>
        )}
        <div
          className={[
            'flex flex-col',
            settled ? '' : 'px-5 py-5 md:px-6',
            hasBoard
              ? 'order-1 border-b border-hairline md:order-2 md:border-b-0 md:border-l'
              : '',
          ].join(' ')}
        >
          {settled ? (
            <ResultPanel
              match={match}
              outcome={outcome}
              opponent={opp?.username ?? 'your opponent'}
              gameUrl={lichessGameUrl(match.host_game_id, yourColor)}
              fresh={fresh}
              onPlayAgain={onPlayAgain}
            />
          ) : (
            <LivePanel
              match={match}
              state={state}
              line={status.line}
              gameUrl={gameUrl}
              opponent={opp?.username ?? 'your opponent'}
            />
          )}
        </div>
      </div>
    </Card>
  );
}

function stageStatus(
  match: MatchView,
  state: BoardState,
  outcome: MatchOutcome | null,
): { word: string; live: boolean; line: string | null } {
  if (outcome) return { word: 'Final', live: false, line: null };
  const live = match.live;
  if (live?.status === 'finished')
    return {
      word: 'Settling',
      live: true,
      line: `Game over · ${resultLine(live.result, live.termination)}`,
    };
  if (state === 'live') {
    const whose =
      live?.turn === 'you' ? 'your move' : live?.turn === 'opp' ? 'their move' : '';
    return {
      word: 'Live',
      live: true,
      line: [`Move ${live?.moves ?? 0}`, whose].filter(Boolean).join(' · '),
    };
  }
  if (state === 'waiting')
    return { word: 'Match on', live: true, line: 'Waiting for the first move' };
  return { word: 'Match on', live: true, line: null };
}

function BoardColumn({
  match,
  state,
  you,
  opp,
  outcome,
}: {
  match: MatchView;
  state: BoardState;
  you: MatchPlayerView | undefined;
  opp: MatchPlayerView | undefined;
  outcome: MatchOutcome | null;
}) {
  const live = match.live;
  const clocks = useLiveClocks(live);
  const orientation = live?.your_color === 'black' ? 'black' : 'white';
  const oppColor = orientation === 'white' ? 'black' : 'white';
  const result = live?.result ?? null;
  const san = live?.san ?? [];

  return (
    <div className="mx-auto flex w-full max-w-[26rem] flex-col gap-2.5">
      <PlayerStrip
        name={opp?.username ?? 'Opponent'}
        rating={opp?.rating}
        color={oppColor}
        clockMs={clocks?.opp}
        running={clocks?.running === 'opp'}
        dim={(outcome === 'win' || result === 'you') && state === 'finished'}
      />
      <div
        className="relative aspect-square w-full overflow-hidden rounded-inset border border-hairline"
        data-testid="board-frame"
      >
        <Suspense fallback={<Skeleton className="h-full w-full rounded-none" />}>
          <div
            className={`h-full w-full transition-opacity duration-500 ${
              state === 'waiting' ? 'opacity-50' : ''
            }`}
          >
            <ChessBoard
              san={san}
              orientation={orientation}
              state={
                state === 'finished'
                  ? 'finished'
                  : state === 'waiting'
                    ? 'waiting'
                    : 'live'
              }
            />
          </div>
        </Suspense>
        {state === 'waiting' && (
          <div className="absolute inset-0 grid place-items-center">
            <span className="rounded-pill border border-line-strong bg-overlay px-3.5 py-1.5 text-xs font-medium text-text shadow-overlay">
              Waiting for the first move
            </span>
          </div>
        )}
      </div>
      <PlayerStrip
        you
        name="You"
        rating={you?.rating}
        color={orientation}
        clockMs={clocks?.you}
        running={clocks?.running === 'you'}
        dim={(outcome === 'loss' || result === 'opp') && state === 'finished'}
      />
      <p className="mt-1 text-micro text-text-tertiary">
        {state === 'finished' ? '' : 'Lichess shares a live game a few moves behind. '}
        Pieces: Cburnett, CC BY-SA 3.0.
      </p>
    </div>
  );
}

function PlayerStrip({
  name,
  rating,
  color,
  clockMs,
  running,
  dim,
  you = false,
}: {
  name: string;
  rating: number | null | undefined;
  color: 'white' | 'black';
  clockMs: number | undefined;
  running: boolean;
  dim: boolean;
  you?: boolean;
}) {
  return (
    <div
      className={`flex items-center gap-3 transition-opacity duration-500 ${dim ? 'opacity-55' : ''}`}
      data-testid={you ? 'strip-you' : 'strip-opp'}
    >
      <span
        aria-hidden
        className={`grid h-8 w-8 shrink-0 place-items-center rounded-full text-xs font-bold ${
          you ? 'bg-action text-bg' : 'bg-panel-raised text-text'
        }`}
      >
        {name.slice(0, 1).toUpperCase()}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-text">{name}</p>
        <p className="flex items-center gap-1.5 text-xs text-text-tertiary">
          <span
            aria-hidden
            className={`h-2.5 w-2.5 rounded-[3px] border border-line-strong ${
              color === 'white' ? 'bg-[var(--board-light)]' : 'bg-bg'
            }`}
          />
          <span>
            {color === 'white' ? 'White' : 'Black'}
            {rating != null && (
              <>
                {' · '}
                <span className="num">{rating}</span>
              </>
            )}
          </span>
        </p>
      </div>
      {clockMs != null && (
        <span
          className={[
            'num flex shrink-0 items-center gap-2 rounded-inset border px-2.5 py-1 text-base font-semibold tabular-nums',
            running
              ? 'border-line-strong bg-panel-raised text-text'
              : 'border-hairline text-text-tertiary',
          ].join(' ')}
          aria-label={`${you ? 'Your' : `${name}'s`} clock ${formatClock(clockMs)}`}
          data-running={running || undefined}
        >
          {running && <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-live" />}
          {formatClock(clockMs)}
        </span>
      )}
    </div>
  );
}

function LivePanel({
  match,
  state,
  line,
  gameUrl,
  opponent,
}: {
  match: MatchView;
  state: BoardState;
  line: string | null;
  gameUrl: string | null;
  opponent: string;
}) {
  const fee = match.entry_cents * 2 - match.prize_cents;
  return (
    <div className="flex h-full flex-col gap-5">
      <div>
        <p className="label-money">Winner takes</p>
        <p className="mt-0.5 text-3xl font-semibold">
          <AmountText cents={match.prize_cents} signed={false} money />
        </p>
        <p className="mt-1 text-xs text-text-secondary">
          Pot {formatPoints(match.pot_cents)} · fee{' '}
          <span className="num text-red">{formatPoints(fee)}</span>
        </p>
      </div>

      {line && (
        <p
          className="flex items-center gap-2 text-sm text-text"
          data-testid="stage-line"
        >
          <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-live" />
          {line}
        </p>
      )}

      {(match.live?.san?.length ?? 0) > 0 && <MoveList san={match.live?.san ?? []} />}

      <div className="mt-auto flex flex-col gap-2">
        {gameUrl ? (
          <a
            href={gameUrl}
            target="_blank"
            rel="noreferrer"
            className={`${pillClassName({ size: 'lg', fullWidth: true })} mm-glow`}
          >
            Open game on Lichess ↗
          </a>
        ) : (
          <p className="text-sm text-text-secondary">
            The game link is on its way. Your stake is held safely.
          </p>
        )}
        <p className="text-xs text-text-tertiary">
          {state === 'unavailable'
            ? `The live board isn't available right now. The game still settles from Lichess.`
            : `Only you and ${opponent} can take these seats. It settles from Lichess when the game ends.`}
        </p>
      </div>
    </div>
  );
}

/** The latest moves, numbered, newest last (desktop, where the column has room). */
function MoveList({ san }: { san: string[] }) {
  const rows: { n: number; white: string; black?: string }[] = [];
  for (let i = 0; i < san.length; i += 2)
    rows.push({ n: i / 2 + 1, white: san[i], black: san[i + 1] });
  const shown = rows.slice(-6);
  const lastPly = san.length - 1;
  const tone = (ply: number) => (ply === lastPly ? 'text-text' : 'text-text-tertiary');
  return (
    <div className="hidden md:block" data-testid="move-list">
      <p className="label-neutral mb-1.5">Moves</p>
      <ol className="num grid grid-cols-[2.25rem_1fr_1fr] gap-y-1 rounded-inset border border-hairline px-3 py-2 text-xs">
        {shown.map((r) => (
          <li key={r.n} className="contents">
            <span className="text-text-tertiary">{r.n}.</span>
            <span className={tone((r.n - 1) * 2)}>{r.white}</span>
            <span className={tone((r.n - 1) * 2 + 1)}>{r.black ?? ''}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function ResultPanel({
  match,
  outcome,
  opponent,
  gameUrl,
  fresh,
  onPlayAgain,
}: {
  match: MatchView;
  outcome: MatchOutcome;
  opponent: string;
  gameUrl: string | null;
  fresh: boolean;
  onPlayAgain: () => void;
}) {
  const rematch = useCreateChallenge();
  const fee = match.entry_cents * 2 - match.prize_cents;
  const how = terminationPhrase(match.termination);
  const secs = settleSeconds(match.game_ended_at, match.resolved_at);
  const win = outcome === 'win';
  const friendly = !!match.friendly;

  const figure = win && !friendly ? match.prize_cents : match.entry_cents;
  const [target, setTarget] = useState(fresh ? 0 : figure);
  const amount = useCountUp(target, 900);
  useEffect(() => setTarget(figure), [figure]);

  const headline = {
    win: 'You won',
    loss: 'You lost',
    draw: 'Draw',
    refund: 'No result',
  }[outcome];
  const sub = [
    `vs ${opponent}`,
    outcome === 'refund' ? (how ?? 'the game never finished') : how,
  ]
    .filter(Boolean)
    .join(' · ');
  const note = friendly
    ? 'Friendly · both stakes refunded'
    : {
        win: null,
        loss: 'Your stake',
        draw: 'Both stakes refunded · no fee',
        refund: 'Both stakes refunded',
      }[outcome];
  const announce =
    win && !friendly
      ? `You won ${formatPoints(figure, { long: true })}${how ? ` ${how}` : ''}`
      : `${headline}${how ? ` ${how}` : ''}. ${note ?? ''}`;

  return (
    <div
      className={`flex h-full flex-col px-5 py-5 md:px-6 ${
        win ? 'mm-result-glow' : ''
      } ${fresh ? 'animate-rise' : ''}`}
      data-testid="result-card"
      data-outcome={outcome}
    >
      <p role="status" aria-live="polite" className="sr-only">
        {announce}
      </p>
      <div aria-hidden>
        {win && !friendly ? <WinMark /> : <QuietMark />}
        <p
          className={`mt-4 text-2xl font-semibold ${win ? 'text-text' : 'text-text-secondary'}`}
          data-testid="result-headline"
        >
          {headline}
        </p>
        <p className="mt-0.5 truncate text-sm text-text-secondary">{sub}</p>

        <p className="mt-4 text-3xl font-semibold" data-testid="result-amount">
          {win && !friendly ? (
            <AmountText cents={amount} signed={false} money />
          ) : outcome === 'loss' && !friendly ? (
            <AmountText cents={-amount} />
          ) : (
            <AmountText cents={amount} signed={false} />
          )}
        </p>
        <p className="mt-1 text-xs text-text-secondary">
          {win && !friendly ? (
            <>
              Pot {formatPoints(match.pot_cents)} · fee{' '}
              <span className="num text-red">{formatPoints(fee)}</span>
            </>
          ) : (
            note
          )}
        </p>
      </div>

      {secs != null && (
        <p
          className={`mt-4 flex items-center gap-1.5 text-xs text-text-secondary ${
            fresh ? 'mm-fade-late' : ''
          }`}
          data-testid="settled-in"
        >
          <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none">
            <path
              d="M3.5 8.5 6.5 11.5 12.5 5"
              stroke="currentColor"
              strokeWidth={1.75}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Settled from Lichess in{' '}
          <span className="num text-text">{formatDuration(secs)}</span>
        </p>
      )}

      <div className="mt-6 flex flex-col gap-2 md:mt-auto md:pt-6">
        <div className="flex gap-2">
          <PillButton className="flex-1" onClick={onPlayAgain}>
            Play again
          </PillButton>
          <PillButton
            variant="secondary"
            className="flex-1"
            disabled={rematch.isPending || rematch.isSuccess}
            onClick={async () => {
              try {
                await rematch.mutateAsync({ rematch_of: match.id });
                toast.success(`Rematch sent to ${opponent}`);
              } catch {
                // Surfaced by the global mutation-error toast.
              }
            }}
          >
            {rematch.isSuccess ? 'Rematch sent' : 'Rematch'}
          </PillButton>
        </div>
        {gameUrl && (
          <a
            href={gameUrl}
            target="_blank"
            rel="noreferrer"
            className={pillClassName({ variant: 'text', fullWidth: true })}
          >
            View game on Lichess ↗
          </a>
        )}
      </div>
    </div>
  );
}
