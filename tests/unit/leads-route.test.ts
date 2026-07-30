import { describe, it, expect, vi, beforeEach } from "vitest"
import { NextRequest } from "next/server"
import { GET } from "../../app/api/leads/route"

const mockQuery = vi.fn()
vi.mock("@/lib/db", () => ({ query: (...args: any[]) => mockQuery(...args) }))
vi.mock("@/lib/campaigns", () => ({ CAMPAIGN_SLUG_TO_ID: { jenex: 1, "shoe-photo": 2, "wp-remediation": 3 } }))
const mockGetIronSession = vi.fn()
vi.mock("iron-session", () => ({ getIronSession: (...args: any[]) => mockGetIronSession(...args) }))
vi.mock("next/headers", () => ({ cookies: () => Promise.resolve({}) }))

describe("GET /api/leads", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetIronSession.mockResolvedValue({ loggedIn: true })
    mockQuery.mockResolvedValue([{ count: "0" }])
  })

  it("returns 401 when not authenticated", async () => {
    mockGetIronSession.mockResolvedValue({ loggedIn: false })
    const req = new NextRequest("http://localhost/api/leads?campaign_id=1")
    const res = await GET(req)
    expect(res.status).toBe(401)
  })

  it("resolves slug campaign_id to numeric ID", async () => {
    mockQuery.mockResolvedValueOnce([{ count: "0" }]).mockResolvedValueOnce([])
    const req = new NextRequest("http://localhost/api/leads?campaign_id=jenex")
    await GET(req)
    expect(mockQuery.mock.calls[0][1]).toContain(1)
  })

  it("applies require_enrichment filter when param=true", async () => {
    mockQuery.mockResolvedValueOnce([{ count: "0" }]).mockResolvedValueOnce([])
    const req = new NextRequest("http://localhost/api/leads?campaign_id=1&require_enrichment=true")
    await GET(req)
    const sql = mockQuery.mock.calls[0][0]
    expect(sql).toContain("enrichment_report IS NOT NULL")
  })

  it("does NOT apply require_enrichment filter by default", async () => {
    mockQuery.mockResolvedValueOnce([{ count: "0" }]).mockResolvedValueOnce([])
    const req = new NextRequest("http://localhost/api/leads?campaign_id=1")
    await GET(req)
    const sql = mockQuery.mock.calls[0][0]
    expect(sql).not.toContain("enrichment_report IS NOT NULL")
  })

  it("caps limit to 200", async () => {
    mockQuery.mockResolvedValueOnce([{ count: "0" }]).mockResolvedValueOnce([])
    const req = new NextRequest("http://localhost/api/leads?campaign_id=1&limit=9999")
    await GET(req)
    const dataQueryParams = mockQuery.mock.calls[1][1]
    expect(dataQueryParams).toContain(200)
  })

  it("returns nextCursor when full page returned", async () => {
    const rows = Array.from({ length: 50 }, (_, i) => ({ id: i + 1 }))
    mockQuery.mockResolvedValueOnce([{ count: "100" }]).mockResolvedValueOnce(rows)
    const req = new NextRequest("http://localhost/api/leads?campaign_id=1")
    const res = await GET(req)
    const body = await res.json()
    expect(body.nextCursor).toBe(50)
  })

  it("applies cursor-based pagination", async () => {
    mockQuery.mockResolvedValueOnce([{ count: "0" }]).mockResolvedValueOnce([])
    const req = new NextRequest("http://localhost/api/leads?campaign_id=1&cursor=42")
    await GET(req)
    const sql = mockQuery.mock.calls[1][0]
    expect(sql).toContain("c.id <")
  })
})
