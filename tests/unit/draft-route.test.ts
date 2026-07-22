import { describe, it, expect, vi, beforeEach } from "vitest"
import { NextRequest } from "next/server"
import { POST } from "../../app/api/leads/draft/route"

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

// Mock LLM chatText
const mockChatText = vi.fn()
vi.mock("@/lib/llm", () => ({
  chatText: (...args: any[]) => mockChatText(...args)
}))

// Mock next/headers
vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({})
}))

describe("POST /api/leads/draft", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetIronSession.mockResolvedValue({ loggedIn: true })
  })

  it("returns 401 if unauthorized", async () => {
    mockGetIronSession.mockResolvedValue({ loggedIn: false })
    const req = new NextRequest("http://localhost:3000/api/leads/draft", {
      method: "POST",
      body: JSON.stringify({ leadId: 1 })
    })
    const res = await POST(req)
    expect(res.status).toBe(401)
  })

  it("returns 400 if leadId is missing", async () => {
    const req = new NextRequest("http://localhost:3000/api/leads/draft", {
      method: "POST",
      body: JSON.stringify({})
    })
    const res = await POST(req)
    expect(res.status).toBe(400)
  })

  it("returns existing draft if already present", async () => {
    mockQuery.mockResolvedValue([{
      candidate_id: 1,
      campaign_id: 2,
      draft_email: "Existing draft here.",
      company_name: "Test Co",
      domain: "test.com",
      rationale: "Good",
      feedback_note: null,
      business_brief: "Brief",
      campaign_name: "Camp"
    }])

    const req = new NextRequest("http://localhost:3000/api/leads/draft", {
      method: "POST",
      body: JSON.stringify({ leadId: 1 })
    })
    const res = await POST(req)
    expect(res.status).toBe(200)
    
    const data = await res.json()
    expect(data.draftEmail).toBe("Existing draft here.")
    // ChatText should not be called
    expect(mockChatText).not.toHaveBeenCalled()
  })

  it("generates new draft and UPSERTs into leads table for pending candidates", async () => {
    // Return candidate without draft
    mockQuery.mockResolvedValueOnce([{
      candidate_id: 1,
      campaign_id: 2,
      draft_email: null,
      company_name: "Test Co",
      domain: "test.com",
      rationale: "Good fit",
      feedback_note: null,
      business_brief: "Campaign brief",
      campaign_name: "Camp"
    }])

    mockChatText.mockResolvedValue({ text: "Hello Test Co, this is a draft." })
    mockQuery.mockResolvedValueOnce([]) // The UPSERT query result

    const req = new NextRequest("http://localhost:3000/api/leads/draft", {
      method: "POST",
      body: JSON.stringify({ leadId: 1 })
    })
    
    const res = await POST(req)
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data.draftEmail).toBe("Hello Test Co, this is a draft.")
    
    // Check if chatText was called with correct context
    expect(mockChatText).toHaveBeenCalledTimes(1)
    
    // Check if UPSERT query was called correctly
    expect(mockQuery).toHaveBeenCalledTimes(2)
    const upsertQuery = mockQuery.mock.calls[1][0]
    expect(upsertQuery).toContain("INSERT INTO leads")
    expect(upsertQuery).toContain("ON CONFLICT (candidate_id)")
    expect(mockQuery.mock.calls[1][1]).toEqual(["Hello Test Co, this is a draft.", 1, 2])
  })
})
