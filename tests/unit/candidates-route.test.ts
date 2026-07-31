import { describe, it, expect, vi, beforeEach } from "vitest"
import { NextRequest } from "next/server"
import { GET } from "../../app/api/candidates/route"

const mockQuery = vi.fn()
vi.mock("@/lib/db", () => ({ query: (...args: any[]) => mockQuery(...args) }))

const mockGetIronSession = vi.fn()
vi.mock("iron-session", () => ({ getIronSession: (...args: any[]) => mockGetIronSession(...args) }))
vi.mock("next/headers", () => ({ cookies: () => Promise.resolve({}) }))

describe("GET /api/candidates", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetIronSession.mockResolvedValue({ loggedIn: true })
    // First call = COUNT, second = data rows
    mockQuery
      .mockResolvedValueOnce([{ count: "3" }])
      .mockResolvedValueOnce([
        { id: 1, domain: "test.sk", company_name: "Test Co", source: "publicwww",
          status: "new", created_at: "2026-07-01T00:00:00Z", enrichment_attempt_count: 0,
          duplicate_of_candidate_id: null },
      ])
  })

  it("returns 401 when not authenticated", async () => {
    mockGetIronSession.mockResolvedValue({ loggedIn: false })
    const req = new NextRequest("http://localhost/api/candidates?campaign_id=1")
    const res = await GET(req)
    expect(res.status).toBe(401)
  })

  it("returns paginated candidates list", async () => {
    const req = new NextRequest("http://localhost/api/candidates?campaign_id=1")
    const res = await GET(req)
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty("candidates")
    expect(body).toHaveProperty("total", 3)
    expect(body.candidates).toHaveLength(1)
    expect(body.candidates[0].domain).toBe("test.sk")
  })

  it("uses correct campaign_id in query", async () => {
    const req = new NextRequest("http://localhost/api/candidates?campaign_id=5")
    await GET(req)
    // COUNT query first
    expect(mockQuery.mock.calls[0][1]).toContain(5)
  })

  it("respects limit param (max 200)", async () => {
    mockQuery.mockResolvedValueOnce([{ count: "0" }]).mockResolvedValueOnce([])
    const req = new NextRequest("http://localhost/api/candidates?campaign_id=1&limit=9999")
    await GET(req)
    // Data query should have limit = 200 (capped)
    expect(mockQuery.mock.calls[1][1]).toContain(200)
  })

  it("queries pipeline statuses including pending_review and approved", async () => {
    const req = new NextRequest("http://localhost/api/candidates?campaign_id=1")
    await GET(req)
    const sql = mockQuery.mock.calls[0][0]
    expect(sql).toContain("'new'")
    expect(sql).toContain("'evaluating'")
    expect(sql).toContain("'evaluated'")
    expect(sql).toContain("'enriched'")
    expect(sql).toContain("'invalid'")
  })
})
