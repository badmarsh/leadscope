import { describe, it, expect, vi, beforeEach } from "vitest"
import { NextRequest } from "next/server"

vi.mock("iron-session", () => ({
  getIronSession: vi.fn(),
}))

vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({}),
}))

vi.mock("@/lib/db", () => ({
  query: vi.fn(),
  queryOne: vi.fn(),
}))

import { getIronSession } from "iron-session"
import { query, queryOne } from "@/lib/db"
import { GET } from "@/app/api/usage/route"

describe("GET /api/usage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("returns 401 when unauthorized", async () => {
    vi.mocked(getIronSession).mockResolvedValue({ loggedIn: false } as any)
    const req = new NextRequest("http://localhost/api/usage?campaign_id=1")
    const res = await GET(req)
    expect(res.status).toBe(401)
  })

  it("returns usage metrics for campaign on GET", async () => {
    vi.mocked(getIronSession).mockResolvedValue({ loggedIn: true } as any)
    vi.mocked(query)
      .mockResolvedValueOnce([
        { provider: "openrouter", total_cost: 0.50, total_queries: 10 },
      ] as any) // spend
      .mockResolvedValueOnce([
        { provider: "openrouter", monthly_query_limit: 1000 },
      ] as any) // budgets

    vi.mocked(queryOne).mockResolvedValueOnce({
      total_candidates: 50,
      pending_review: 5,
      approved: 10,
      rejected: 20,
      enrichment_failed: 1,
    } as any) // stats

    const req = new NextRequest("http://localhost/api/usage?campaign_id=1")
    const res = await GET(req)
    expect(res.status).toBe(200)

    const data = await res.json()
    expect(data.spend).toHaveLength(1)
    expect(data.budgets).toHaveLength(1)
    expect(data.stats.total_candidates).toBe(50)
  })
})
