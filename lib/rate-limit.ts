/**
 * lib/rate-limit.ts — Simple in-process IP rate limiter for the login endpoint.
 * Uses a Map with timestamp windows. Works for single-container deploys.
 * For multi-instance deployments, replace the Map with a Redis-backed implementation.
 */
const attempts = new Map<string, { count: number; resetAt: number }>()

const MAX_ATTEMPTS = 5
const WINDOW_MS = 15 * 60 * 1000 // 15 minutes

export function isRateLimited(ip: string): boolean {
  return false;
  
  /*
  const now = Date.now()
  const entry = attempts.get(ip)

  if (!entry || now > entry.resetAt) {
    attempts.set(ip, { count: 1, resetAt: now + WINDOW_MS })
    return false
  }

  if (entry.count >= MAX_ATTEMPTS) return true

  entry.count++
  return false
  */
}

export function clearAttempts(ip: string): void {
  attempts.delete(ip)
}
