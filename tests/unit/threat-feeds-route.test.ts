import { describe, it, expect, vi, beforeEach } from "vitest"
import { NextRequest } from "next/server"
import { GET } from "../../app/api/threat-feeds/route"

const mockQuery = vi.fn()
vi.mock("@/lib/db", () => ({
  query: (...args: any[]) => mockQuery(...args)
}))

describe("GET /api/threat-feeds", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("returns candidate threat feed items on success", async () => {
    const mockRows = [
      { id: 1, campaign_id: 1, domain: "infected.com", source: "publicwww", status: "evaluated", score: 90 }
    ]
    mockQuery.mockResolvedValueOnce(mockRows)

    const req = new NextRequest("http://localhost/api/threat-feeds")
    const res = await GET(req)

    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.candidates).toHaveLength(1)
    expect(body.candidates[0].domain).toBe("infected.com")
  })

  it("returns 500 when database error occurs", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {})
    mockQuery.mockRejectedValue(new Error("DB connection failure"))

    const req = new NextRequest("http://localhost/api/threat-feeds")
    const res = await GET(req)

    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error).toBe("Internal Server Error")
    consoleSpy.mockRestore()
  })
})
