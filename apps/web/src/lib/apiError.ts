/** The API's own message for a failed call (`{code, message, detail}`), else `fallback`. */
export function messageOf(error: unknown, fallback: string): string {
  const msg = (error as { message?: string } | undefined)?.message;
  return typeof msg === 'string' && msg ? msg : fallback;
}
