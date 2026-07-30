import { describe, it, expect, vi, beforeEach } from "vitest"
import { POST } from "@/app/api/logout/route"

const mockDestroy = vi.fn()
const mockGetIronSession = vi.fn()
vi.mock("iron-session", () => ({
  getIronSession: (...args: any[]) => mockGetIronSession(...args)
}))

vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({})
}))

describe("POST /api/logout", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetIronSession.mockResolvedValue({
      destroy: mockDestroy
    })
  })

  it("destroys session and returns ok", async () => {
    const res = await POST()
    expect(res.status).toBe(200)
    const json = await res.json()
    expect(json).toEqual({ ok: true })
    expect(mockDestroy).toHaveBeenCalledOnce()
  })
})
