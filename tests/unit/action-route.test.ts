import { describe, it, expect, vi, beforeEach } from "vitest"
import { NextRequest } from "next/server"
import { POST, PATCH } from "../../app/api/action/route"

const mockClientQuery = vi.fn()
const mockClientRelease = vi.fn()

vi.mock("@/lib/db", () => ({
  pool: {
    connect: vi.fn(() => Promise.resolve({
      query: mockClientQuery,
      release: mockClientRelease
    }))
  }
}))

const mockGetIronSession = vi.fn()
vi.mock("iron-session", () => ({
  getIronSession: (...args: any[]) => mockGetIronSession(...args)
}))

vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({})
}))

describe("/api/action", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetIronSession.mockResolvedValue({ loggedIn: true, username: "admin" })
    mockClientQuery.mockResolvedValue({ rows: [] })
  })

  describe("POST /api/action", () => {
    it("returns 401 when unauthorized", async () => {
      mockGetIronSession.mockResolvedValue({ loggedIn: false })
      const req = new NextRequest("http://localhost/api/action", {
        method: "POST",
        body: JSON.stringify({ candidate_id: 1, decision: "approved" })
      })
      const res = await POST(req)
      expect(res.status).toBe(401)
    })

    it("returns 400 when body is invalid", async () => {
      const req = new NextRequest("http://localhost/api/action", {
        method: "POST",
        body: JSON.stringify({ candidate_id: "invalid", decision: "maybe" })
      })
      const res = await POST(req)
      expect(res.status).toBe(400)
    })

    it("processes decision approval and writes feedback, tokens, and lead row", async () => {
      // Mock DNC check -> empty (not on DNC)
      // Mock feedback check -> empty (not existing)
      // Mock campInfo -> domain & settings
      mockClientQuery
        .mockResolvedValueOnce({ rows: [] }) // BEGIN
        .mockResolvedValueOnce({ rows: [] }) // DNC check
        .mockResolvedValueOnce({ rows: [] }) // feedback check
        .mockResolvedValueOnce({ rows: [] }) // INSERT feedback
        .mockResolvedValueOnce({ rows: [] }) // UPDATE candidate status
        .mockResolvedValueOnce({ rows: [] }) // UPDATE audit_token
        .mockResolvedValueOnce({ rows: [] }) // INSERT leads
        .mockResolvedValueOnce({ rows: [{ settings: { webhook_url: "https://example.com/webhook" }, domain: "example.com" }] }) // campInfo
        .mockResolvedValueOnce({ rows: [] }) // COMMIT

      const req = new NextRequest("http://localhost/api/action", {
        method: "POST",
        body: JSON.stringify({ candidate_id: 1, decision: "approved", note: "Great candidate" })
      })
      const res = await POST(req)
      expect(res.status).toBe(200)
      const body = await res.json()
      expect(body.ok).toBe(true)
      expect(mockClientRelease).toHaveBeenCalled()
    })

    it("auto-rejects when candidate is on DNC list", async () => {
      mockClientQuery
        .mockResolvedValueOnce({ rows: [] }) // BEGIN
        .mockResolvedValueOnce({ rows: [{ 1: 1 }] }) // DNC check -> found!
        .mockResolvedValueOnce({ rows: [] }) // feedback check
        .mockResolvedValueOnce({ rows: [] }) // INSERT feedback with rejected
        .mockResolvedValueOnce({ rows: [] }) // UPDATE candidate status to rejected
        .mockResolvedValueOnce({ rows: [] }) // COMMIT

      const req = new NextRequest("http://localhost/api/action", {
        method: "POST",
        body: JSON.stringify({ candidate_id: 1, decision: "approved" })
      })
      const res = await POST(req)
      expect(res.status).toBe(200)

      // Ensure UPDATE candidate status called with 'rejected'
      const updateCall = mockClientQuery.mock.calls.find((c: any[]) => c[0].includes("UPDATE candidates SET status = $1"))
      expect(updateCall).toBeDefined()
      expect(updateCall![1][0]).toBe("rejected")
    })

    it("returns 500 when transaction fails", async () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {})
      mockClientQuery.mockRejectedValueOnce(new Error("DB deadlock"))

      const req = new NextRequest("http://localhost/api/action", {
        method: "POST",
        body: JSON.stringify({ candidate_id: 1, decision: "rejected" })
      })
      const res = await POST(req)
      expect(res.status).toBe(500)
      consoleSpy.mockRestore()
    })
  })

  describe("PATCH /api/action", () => {
    it("returns 401 when unauthorized", async () => {
      mockGetIronSession.mockResolvedValue({ loggedIn: false })
      const req = new NextRequest("http://localhost/api/action", {
        method: "PATCH",
        body: JSON.stringify({ candidate_id: 1 })
      })
      const res = await PATCH(req)
      expect(res.status).toBe(401)
    })

    it("resets candidate status and enrichment state on reopen", async () => {
      mockClientQuery
        .mockResolvedValueOnce({ rows: [] }) // BEGIN
        .mockResolvedValueOnce({ rows: [] }) // UPDATE candidates
        .mockResolvedValueOnce({ rows: [] }) // UPDATE leads
        .mockResolvedValueOnce({ rows: [] }) // COMMIT

      const req = new NextRequest("http://localhost/api/action", {
        method: "PATCH",
        body: JSON.stringify({ candidate_id: 42 })
      })
      const res = await PATCH(req)
      expect(res.status).toBe(200)
      const body = await res.json()
      expect(body.ok).toBe(true)

      const resetCandidateCall = mockClientQuery.mock.calls.find((c: any[]) => c[0].includes("SET status = 'pending_review'"))
      expect(resetCandidateCall).toBeDefined()
      expect(resetCandidateCall![1][0]).toBe(42)
    })
  })
})
