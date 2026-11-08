export function middlePreset(presets: readonly number[]): number {
  return presets[Math.floor(presets.length / 2)] ?? presets[0];
}
