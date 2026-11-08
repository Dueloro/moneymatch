import { speedName } from './timeControl';

export function lookingFor(speed: string | null | undefined): string {
  if (!speed) return 'is looking for a game';
  const name = speedName(speed).toLowerCase();
  return `is looking for ${/^[aeiou]/.test(name) ? 'an' : 'a'} ${name} game`;
}
