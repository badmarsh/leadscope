import { describe, it, expect, vi, beforeEach } from "vitest"
import { GET } from "@/app/api/session/route"

const mockGetIronSession = vi.fn()
vi.mock("iron-session", () => ({
  getIronSession: (...args: any[]) => mockGetIronSession(...args)
}))

vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({})
}))

describe("GET /api/session", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("returns { loggedIn: true } when session is logged in", async () => {
    mockGetIronSession.mockResolvedValue({ loggedIn: true })
    const res = await GET()
    expect(res.status).toBe(200)
    const json = await res.json()
    expect(json).toEqual({ loggedIn: true })
  })

  it("returns { loggedIn: false } when session is not logged in", async () => {
    mockGetIronSession.mockResolvedValue({ loggedIn: false })
    const res = await GET()
    expect(res.status).toBe(200)
    const json = await res.json()
    expect(json).toEqual({ loggedIn: false })
  })
})
