import { describe, it, expect, vi, beforeEach } from "vitest"
import { NextRequest } from "next/server"

vi.mock("iron-session", () => ({
  getIronSession: vi.fn(),
}))

vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({}),
}))

vi.mock("@/lib/db", () => ({
  queryOne: vi.fn(),
  pool: {
    query: vi.fn(),
  },
}))

import { getIronSession } from "iron-session"
import { queryOne, pool } from "@/lib/db"
import { GET, PUT } from "@/app/api/campaigns/[id]/settings/route"

describe("/api/campaigns/[id]/settings", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("returns 401 when unauthorized", async () => {
    vi.mocked(getIronSession).mockResolvedValue({ loggedIn: false } as any)
    const req = new NextRequest("http://localhost/api/campaigns/1/settings")
    const res = await GET(req, { params: Promise.resolve({ id: "1" }) })
    expect(res.status).toBe(401)
  })

  it("returns 404 when campaign not found", async () => {
    vi.mocked(getIronSession).mockResolvedValue({ loggedIn: true } as any)
    vi.mocked(queryOne).mockResolvedValue(null)
    const req = new NextRequest("http://localhost/api/campaigns/999/settings")
    const res = await GET(req, { params: Promise.resolve({ id: "999" }) })
    expect(res.status).toBe(404)
  })

  it("returns merged settings on GET", async () => {
    vi.mocked(getIronSession).mockResolvedValue({ loggedIn: true } as any)
    vi.mocked(queryOne).mockResolvedValue({
      settings: { search_cooldown_days: 15 },
      business_brief: "Brief text",
    })
    const req = new NextRequest("http://localhost/api/campaigns/1/settings")
    const res = await GET(req, { params: Promise.resolve({ id: "1" }) })
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data.settings.search_cooldown_days).toBe(15)
    expect(data.settings.min_score_for_review).toBe(60) // default
    expect(data.business_brief).toBe("Brief text")
  })

  it("validates and updates settings on PUT", async () => {
    vi.mocked(getIronSession).mockResolvedValue({ loggedIn: true } as any)
    vi.mocked(pool.query).mockResolvedValue({ rowCount: 1 } as any)

    const req = new NextRequest("http://localhost/api/campaigns/1/settings", {
      method: "PUT",
      body: JSON.stringify({
        search_cooldown_days: 10,
        business_brief: "Updated brief",
      }),
    })
    const res = await PUT(req, { params: Promise.resolve({ id: "1" }) })
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data.ok).toBe(true)
    expect(data.settings.search_cooldown_days).toBe(10)
  })

  it("rejects invalid setting values on PUT", async () => {
    vi.mocked(getIronSession).mockResolvedValue({ loggedIn: true } as any)

    const req = new NextRequest("http://localhost/api/campaigns/1/settings", {
      method: "PUT",
      body: JSON.stringify({
        search_cooldown_days: -5, // out of range (min 1)
      }),
    })
    const res = await PUT(req, { params: Promise.resolve({ id: "1" }) })
    expect(res.status).toBe(400)
    const data = await res.json()
    expect(data.error).toContain("must be between 1 and 365")
  })
})
