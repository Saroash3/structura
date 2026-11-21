import "server-only";

/**
 * Light in-memory rate limit for login attempts: max 5 failures per key per 15 minutes.
 * Good enough for a single server; use Redis or similar if you run several instances.
 */
const WINDOW_MS = 15 * 60 * 1000;
const MAX_FAILURES = 5;
const failures = new Map<string, number[]>();

function recent(key: string): number[] {
  const now = Date.now();
  const list = (failures.get(key) ?? []).filter((t) => now - t < WINDOW_MS);
  failures.set(key, list);
  return list;
}

export function isRateLimited(key: string): boolean {
  return recent(key).length >= MAX_FAILURES;
}

export function recordFailure(key: string): void {
  recent(key).push(Date.now());
}

export function clearFailures(key: string): void {
  failures.delete(key);
}
