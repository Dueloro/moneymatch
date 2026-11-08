import { bandAt, MAX_BAND } from '../../lib/skillBand';

const TICKS = Array.from({ length: 17 }, (_, i) => i * 100 - MAX_BAND);
const AXIS = [-MAX_BAND, -MAX_BAND / 2, 0, MAX_BAND / 2, MAX_BAND];

/**
 * Your rating at the centre of a ±800 ruler, the pairing band shaded around it
 * and widening as you wait. `rating` null draws the band relative to you.
 */
export function SkillBandRuler({
  rating,
  seconds,
}: {
  rating: number | null;
  seconds: number;
}) {
  const band = bandAt(seconds);
  const width = (band / MAX_BAND) * 100;
  const label = (offset: number) =>
    rating != null
      ? String(rating + offset)
      : offset === 0
        ? 'You'
        : `${offset > 0 ? '+' : '−'}${Math.abs(offset)}`;

  return (
    <div data-testid="skill-band-ruler">
      <div className="relative h-12" aria-hidden>
        <div className="absolute inset-x-0 top-1/2 h-px bg-hairline" />
        {TICKS.map((t) => (
          <span
            key={t}
            className={[
              'absolute top-1/2 w-px -translate-y-1/2',
              t % 400 === 0 ? 'h-4 bg-line-strong' : 'h-2 bg-hairline',
            ].join(' ')}
            style={{ left: `${((t + MAX_BAND) / (2 * MAX_BAND)) * 100}%` }}
          />
        ))}
        <div
          className="absolute inset-y-1 rounded-inset border-x border-[color-mix(in_srgb,var(--live)_70%,transparent)] bg-[color-mix(in_srgb,var(--live)_25%,transparent)] motion-safe:transition-[left,width] motion-safe:duration-1000 motion-safe:ease-linear"
          style={{ left: `${50 - width / 2}%`, width: `${width}%` }}
          data-testid="skill-band"
        />
        <span className="absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 rounded-full bg-text" />
      </div>
      <div className="relative mt-1 h-4" aria-hidden>
        {AXIS.map((o, i) => (
          <span
            key={o}
            className={[
              'num absolute text-micro',
              o === 0 ? 'text-text' : 'text-text-tertiary',
              i === 0
                ? 'left-0'
                : i === AXIS.length - 1
                  ? 'right-0'
                  : '-translate-x-1/2',
            ].join(' ')}
            style={
              i === 0 || i === AXIS.length - 1
                ? undefined
                : { left: `${((o + MAX_BAND) / (2 * MAX_BAND)) * 100}%` }
            }
          >
            {label(o)}
          </span>
        ))}
      </div>
    </div>
  );
}
