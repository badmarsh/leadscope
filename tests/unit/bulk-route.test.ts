import { describe, it, expect, vi, beforeEach } from "vitest"
import { NextRequest } from "next/server"
import { POST } from "../../app/api/action/bulk/route"

// Mock the db query
const mockQuery = vi.fn()
vi.mock("@/lib/db", () => ({
  query: (...args: any[]) => mockQuery(...args)
}))

// Mock iron-session
const mockGetIronSession = vi.fn()
vi.mock("iron-session", () => ({
  getIronSession: (...args: any[]) => mockGetIronSession(...args)
}))

// Mock next/headers
vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({})
}))

describe("POST /api/action/bulk", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetIronSession.mockResolvedValue({ loggedIn: true, username: "test_user" })
    mockQuery.mockResolvedValue([])
  })

  it("returns 401 if unauthorized", async () => {
    mockGetIronSession.mockResolvedValue({ loggedIn: false })
    const req = new NextRequest("http://localhost:3000/api/action/bulk", {
      method: "POST",
      body: JSON.stringify({ decision: "rerun_evaluation", candidate_ids: [1] })
    })
    const res = await POST(req)
    expect(res.status).toBe(401)
  })

  it("returns 400 if action is invalid", async () => {
    const req = new NextRequest("http://localhost:3000/api/action/bulk", {
      method: "POST",
      body: JSON.stringify({ decision: "invalid_action", candidate_ids: [1] })
    })
    const res = await POST(req)
    expect(res.status).toBe(400)
  })

  it("handles rerun_evaluation without SQL column errors", async () => {
    // Mock the lockedRows return value for SKIP LOCKED
    mockQuery.mockResolvedValueOnce([{ id: 1 }, { id: 2 }])
    const req = new NextRequest("http://localhost:3000/api/action/bulk", {
      method: "POST",
      body: JSON.stringify({ decision: "rerun_evaluation", candidate_ids: [1, 2] })
    })
    const res = await POST(req)
    expect(res.status).toBe(200)

    // Check what SQL was called
    expect(mockQuery).toHaveBeenCalled()
    // First query is the lock, second is the update
    const sql = mockQuery.mock.calls[1][0]
    expect(sql).not.toContain("search_attempted_at")
    expect(sql).toContain("status = 'new'")
    expect(sql).toContain("processing_generation = processing_generation + 1")
    expect(sql).toContain("lease_id = NULL")
    expect(sql).toContain("id = ANY($1::int[])")
  })

  it("handles rerun_enrichment properly", async () => {
    // Mock the lockedRows return value for SKIP LOCKED
    mockQuery.mockResolvedValueOnce([{ id: 1 }, { id: 2 }])
    const req = new NextRequest("http://localhost:3000/api/action/bulk", {
      method: "POST",
      body: JSON.stringify({ decision: "rerun_enrichment", candidate_ids: [1, 2] })
    })
    const res = await POST(req)
    expect(res.status).toBe(200)

    // Rerun enrichment executes 3 queries: lock candidate rows, update candidate status, delete from leads
    expect(mockQuery).toHaveBeenCalledTimes(3)
    expect(mockQuery.mock.calls[1][0]).toContain("CASE WHEN status = 'enrichment_failed' THEN 'evaluated'")
    expect(mockQuery.mock.calls[1][0]).toContain("processing_generation = processing_generation + 1")
    expect(mockQuery.mock.calls[1][0]).toContain("lease_id = NULL")
    expect(mockQuery.mock.calls[2][0]).toContain("DELETE FROM leads")
  })

  it("handles approved properly and creates feedback", async () => {
    const req = new NextRequest("http://localhost:3000/api/action/bulk", {
      method: "POST",
      body: JSON.stringify({ decision: "approved", candidate_ids: [1] })
    })
    const res = await POST(req)
    expect(res.status).toBe(200)

    // Checks feedback insertion (first query)
    expect(mockQuery.mock.calls[0][0]).toContain("INSERT INTO feedback")
    expect(mockQuery.mock.calls[0][1]).toEqual([[1], "approved", "test_user_bulk"])
    
    // Checks candidate update (second query)
    expect(mockQuery.mock.calls[1][0]).toContain("status = $1")
    expect(mockQuery.mock.calls[1][1]).toEqual(["approved", [1]])
  })
})
