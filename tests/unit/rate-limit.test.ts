import { describe, it, expect, beforeEach, vi } from "vitest"
import { isRateLimited, clearAttempts } from "@/lib/rate-limit"

describe("isRateLimited", () => {
  beforeEach(() => {
    clearAttempts("test-ip")
    clearAttempts("other-ip")
  })

  it("allows first 5 attempts from the same IP", () => {
    for (let i = 0; i < 5; i++) {
      expect(isRateLimited("test-ip")).toBe(false)
    }
  })

  it("blocks the 6th attempt", () => {
    for (let i = 0; i < 5; i++) isRateLimited("test-ip")
    expect(isRateLimited("test-ip")).toBe(true)
  })

  it("does not block a different IP", () => {
    for (let i = 0; i < 5; i++) isRateLimited("test-ip")
    expect(isRateLimited("other-ip")).toBe(false)
  })

  it("clearAttempts resets the counter", () => {
    for (let i = 0; i < 5; i++) isRateLimited("test-ip")
    expect(isRateLimited("test-ip")).toBe(true)
    clearAttempts("test-ip")
    expect(isRateLimited("test-ip")).toBe(false)
  })

  it("resets automatically after the 15-minute window expires", () => {
    vi.useFakeTimers()
    for (let i = 0; i < 5; i++) isRateLimited("test-ip")
    expect(isRateLimited("test-ip")).toBe(true)
    vi.advanceTimersByTime(16 * 60 * 1000)
    expect(isRateLimited("test-ip")).toBe(false)
    vi.useRealTimers()
  })
})
