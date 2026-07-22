import { Link, Navigate } from 'react-router-dom';

import { useAuth } from '../auth/useAuth';
import { VersusCard } from '../components/play/VersusCard';
import { GlowBackdrop, Logo } from '../components/ui/brand';
import { PillButton } from '../components/ui/PillButton';

/**
 * Public marketing landing at `/`. Gives a cold visitor the context the signed-
 * in app can't (what Money Match is, how it works, who can play) before asking for
 * auth. Signed-in users skip straight to Play. The external marketing site can
 * also link directly to `/signin` and bypass this page.
 */
export function LandingPage() {
  const { session, loading } = useAuth();
  if (!loading && session) return <Navigate to="/play" replace />;

  return (
    <div className="relative min-h-screen bg-bg text-text">
      <GlowBackdrop />
      <div className="relative z-10">
        <TopNav />
        <main>
          <Hero />
          <Marquee />
          <HowItWorks />
          <Games />
          <Trust />
          <FinalCta />
        </main>
        <Footer />
      </div>
    </div>
  );
}

function TopNav() {
  return (
    <header className="sticky top-0 z-20 border-b border-hairline bg-bg/70 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 md:px-8">
        <Logo />
        <div className="flex items-center gap-2">
          <a
            href="#how"
            className="hidden px-3 py-2 text-sm text-text-secondary hover:text-text sm:block"
          >
            How it works
          </a>
          <a
            href="#fair"
            className="hidden px-3 py-2 text-sm text-text-secondary hover:text-text sm:block"
          >
            Fairness
          </a>
          <Link to="/signin">
            <PillButton>Enter the beta</PillButton>
          </Link>
        </div>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="mx-auto max-w-6xl px-5 pb-16 pt-14 md:px-8 md:pb-24 md:pt-20">
      <div className="grid items-center gap-12 md:grid-cols-2">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-pill bg-green px-3 py-1 text-xs font-bold uppercase tracking-wide text-black">
              Open beta · Season 01
            </span>
            <span className="label-mono">Skill-based · Peer-to-peer · Flat rake</span>
          </div>

          <h1 className="mt-6 text-5xl font-bold leading-[0.98] tracking-tight sm:text-6xl">
            Put your <span className="mark">skill</span>
            <br />
            on the line.
          </h1>
          <p className="mt-6 max-w-md text-base text-text-secondary sm:text-lg">
            Real stakes on your own matches. Play the games you already play, stake into
            a shared pot, and the winner takes it minus a flat fee. No house, no odds.
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Link to="/signin" className="w-full sm:w-auto">
              <PillButton fullWidth>Enter the beta</PillButton>
            </Link>
            <a href="#how" className="w-full sm:w-auto">
              <PillButton variant="outline" fullWidth>
                See how it works
              </PillButton>
            </a>
          </div>
          <p className="mt-5 text-xs text-text-tertiary">
            18+. Cash play available in eligible U.S. states.
          </p>
        </div>

        <div className="mx-auto w-full max-w-sm">
          <VersusCard
            marketLabel="Chess · Blitz"
            status="Live match"
            you={{ name: 'you', rating: 1842 }}
            opponent={{ name: 'knight_or_flight', rating: 1855 }}
            potCents={2000}
            prizeCents={1800}
          />
        </div>
      </div>
    </section>
  );
}

const CONTESTS = [
  'Chess · $5',
  'CS2 · $25',
  'Dota 2 · $40',
  'Chess · $10',
  'CS2 · $10',
  'Chess · $25',
  'Dota 2 · $20',
  'CS2 · $50',
];

function Marquee() {
  const chip = (key: string, label: string) => (
    <span
      key={key}
      className="mx-3 inline-flex items-center gap-2 rounded-pill border border-hairline px-4 py-1.5 text-sm"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-green" aria-hidden />
      {label}
    </span>
  );
  return (
    <div className="relative overflow-hidden border-y border-hairline bg-panel/40 py-3">
      <div className="flex w-max animate-marquee whitespace-nowrap">
        {CONTESTS.map((c, i) => chip(`a-${i}`, c))}
        {CONTESTS.map((c, i) => chip(`b-${i}`, c))}
      </div>
    </div>
  );
}

const STEPS = [
  {
    n: '01',
    title: 'Link your game',
    body: 'Connect an account like Chess on Lichess. Results are read straight from the official game API, never self-reported.',
  },
  {
    n: '02',
    title: 'Stake into the pot',
    body: 'Get matched with an evenly-skilled opponent and each stake the same entry. Both entries escrow into one shared pot.',
  },
  {
    n: '03',
    title: 'Winner takes the pot',
    body: 'Play your real match. We settle it automatically and pay the winner the pot minus a flat fee. That fee is all we make.',
  },
];

function HowItWorks() {
  return (
    <section id="how" className="mx-auto max-w-6xl px-5 py-16 md:px-8 md:py-24">
      <p className="label-mono">How it works</p>
      <h2 className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl">
        A duel in three steps.
      </h2>
      <div className="mt-10 grid gap-4 md:grid-cols-3">
        {STEPS.map((s) => (
          <div key={s.n} className="rounded-2xl border border-hairline bg-panel p-6">
            <div className="font-mono text-2xl font-bold text-green">{s.n}</div>
            <h3 className="mt-4 text-lg font-semibold">{s.title}</h3>
            <p className="mt-2 text-sm text-text-secondary">{s.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

const GAMES = [
  { name: 'Chess', sub: 'via Lichess', live: true },
  { name: 'CS2', sub: 'via FACEIT', live: false },
  { name: 'Dota 2', sub: 'via OpenDota', live: false },
];

function Games() {
  return (
    <section className="border-t border-hairline">
      <div className="mx-auto max-w-6xl px-5 py-16 md:px-8 md:py-24">
        <p className="label-mono">Games</p>
        <h2 className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl">
          Games you already play.
        </h2>
        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          {GAMES.map((g) => (
            <div
              key={g.name}
              className="flex items-center justify-between rounded-2xl border border-hairline bg-panel p-6"
            >
              <div>
                <h3 className="text-lg font-semibold">{g.name}</h3>
                <p className="mt-1 text-sm text-text-secondary">{g.sub}</p>
              </div>
              <span
                className={[
                  'rounded-pill px-3 py-1 text-xs font-bold uppercase tracking-wide',
                  g.live
                    ? 'bg-green text-black'
                    : 'border border-hairline text-text-secondary',
                ].join(' ')}
              >
                {g.live ? 'Live' : 'Soon'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const TRUST = [
  {
    title: 'No house, ever',
    body: 'Every contest resolves on the players’ own play. We never set a line or take a side.',
  },
  {
    title: 'Host-verified results',
    body: 'Outcomes are read from the official game API, so no one can report a result that did not happen.',
  },
  {
    title: 'Flat, visible fee',
    body: 'You see the exact rake before you commit. It is the only way we make money.',
  },
  {
    title: 'Fair matchmaking',
    body: 'Players are paired within a skill band, so a match is a genuine contest rather than a mismatch.',
  },
];

function Trust() {
  return (
    <section id="fair" className="border-t border-hairline">
      <div className="mx-auto max-w-6xl px-5 py-16 md:px-8 md:py-24">
        <p className="label-mono">Fairness</p>
        <h2 className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl">
          We hold the pot. We never take a side.
        </h2>
        <div className="mt-10 grid gap-x-10 gap-y-8 sm:grid-cols-2">
          {TRUST.map((t) => (
            <div key={t.title} className="border-t border-hairline pt-5">
              <h3 className="text-base font-semibold text-green">{t.title}</h3>
              <p className="mt-2 max-w-md text-sm text-text-secondary">{t.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function FinalCta() {
  return (
    <section className="border-t border-hairline">
      <div className="mx-auto max-w-6xl px-5 py-20 text-center md:px-8 md:py-28">
        <h2 className="text-4xl font-bold tracking-tight sm:text-6xl">
          Stake. Play. <span className="mark">Get paid.</span>
        </h2>
        <p className="mx-auto mt-5 max-w-md text-sm text-text-secondary">
          Join the beta, link a game, and play your first match in minutes.
        </p>
        <div className="mt-8 flex justify-center">
          <Link to="/signin" className="w-full sm:w-auto">
            <PillButton fullWidth>Enter the beta</PillButton>
          </Link>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-hairline">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-10 text-sm text-text-tertiary md:flex-row md:items-center md:justify-between md:px-8">
        <Logo />
        <p className="max-w-md">
          Money Match is a neutral operator of peer-to-peer skill contests. 18+. Cash
          play is available in eligible U.S. states only; free play is available
          everywhere.
        </p>
        <p>&copy; {new Date().getFullYear()} Money Match</p>
      </div>
    </footer>
  );
}
