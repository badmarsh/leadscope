import { describe, it, expect, vi, beforeEach } from "vitest"
import { NextRequest } from "next/server"
import { GET } from "../../app/api/audit/[token]/route"

const mockQuery = vi.fn()
vi.mock("@/lib/db", () => ({
  query: (...args: any[]) => mockQuery(...args)
}))

describe("GET /api/audit/[token]", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("returns 400 when token is missing or too short", async () => {
    const req = new NextRequest("http://localhost/api/audit/short_token")
    const res = await GET(req, { params: Promise.resolve({ token: "short_token" }) })
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error).toBe("Invalid token")
  })

  it("returns 404 when audit token is not found", async () => {
    mockQuery.mockResolvedValueOnce([])
    const validToken = "a".repeat(32)
    const req = new NextRequest(`http://localhost/api/audit/${validToken}`)
    const res = await GET(req, { params: Promise.resolve({ token: validToken }) })
    expect(res.status).toBe(404)
  })

  it("returns candidate audit details and increments view count", async () => {
    const validToken = "b".repeat(32)
    mockQuery
      .mockResolvedValueOnce([
        {
          domain: "example.com",
          company_name: "Example Corp",
          score: 85,
          rationale: "High risk vulnerability found",
          evidence_data: JSON.stringify({ malware_family: "wp_eval", confidence: "high" }),
          audit_view_count: 3
        }
      ])
      .mockResolvedValueOnce([]) // UPDATE view count

    const req = new NextRequest(`http://localhost/api/audit/${validToken}`)
    const res = await GET(req, { params: Promise.resolve({ token: validToken }) })
    
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.domain).toBe("example.com")
    expect(body.score).toBe(85)
    expect(body.evidence.malware_family).toBe("wp_eval")
    expect(body.view_count).toBe(4)

    // Check update query was called with token
    expect(mockQuery).toHaveBeenCalledTimes(2)
    expect(mockQuery.mock.calls[1][1]).toEqual([validToken])
  })
})
