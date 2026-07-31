import { describe, it, expect, vi, beforeEach } from "vitest"
import { NextRequest } from "next/server"
import { POST } from "../../app/api/campaigns/[id]/pipeline/route"

const mockQuery = vi.fn()
const mockQueryOne = vi.fn()
vi.mock("@/lib/db", () => ({
  query: (...args: any[]) => mockQuery(...args),
  queryOne: (...args: any[]) => mockQueryOne(...args)
}))

const mockGetIronSession = vi.fn()
vi.mock("iron-session", () => ({
  getIronSession: (...args: any[]) => mockGetIronSession(...args)
}))

vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({})
}))

const mockFetch = vi.fn()
vi.stubGlobal("fetch", mockFetch)

describe("POST /api/campaigns/[id]/pipeline", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetIronSession.mockResolvedValue({ loggedIn: true })
  })

  it("returns 401 when unauthorized", async () => {
    mockGetIronSession.mockResolvedValue({ loggedIn: false })
    const req = new NextRequest("http://localhost/api/campaigns/1/pipeline", {
      method: "POST",
      body: JSON.stringify({ action: "start", stage: "stage1" })
    })
    const res = await POST(req, { params: Promise.resolve({ id: "1" }) })
    expect(res.status).toBe(401)
  })

  it("returns 400 for invalid action or stage", async () => {
    const req = new NextRequest("http://localhost/api/campaigns/1/pipeline", {
      method: "POST",
      body: JSON.stringify({ action: "invalid", stage: "stage1" })
    })
    const res = await POST(req, { params: Promise.resolve({ id: "1" }) })
    expect(res.status).toBe(400)
  })

  it("sends stop signal when action is stop", async () => {
    mockQuery.mockResolvedValueOnce([])
    const req = new NextRequest("http://localhost/api/campaigns/1/pipeline", {
      method: "POST",
      body: JSON.stringify({ action: "stop", stage: "stage2" })
    })
    const res = await POST(req, { params: Promise.resolve({ id: "1" }) })
    expect(res.status).toBe(200)
    expect(mockQuery).toHaveBeenCalledWith(
      "UPDATE campaigns SET stage2_status = 'stopping' WHERE id = $1",
      [1]
    )
  })

  it("returns 409 if stage is already running or stopping", async () => {
    mockQueryOne.mockResolvedValueOnce({ current_status: "running" })
    const req = new NextRequest("http://localhost/api/campaigns/1/pipeline", {
      method: "POST",
      body: JSON.stringify({ action: "start", stage: "stage3" })
    })
    const res = await POST(req, { params: Promise.resolve({ id: "1" }) })
    expect(res.status).toBe(409)
  })

  it("triggers backend service when starting idle stage", async () => {
    mockQueryOne.mockResolvedValueOnce({ current_status: "idle" })
    mockFetch.mockResolvedValueOnce({ ok: true })

    const req = new NextRequest("http://localhost/api/campaigns/1/pipeline", {
      method: "POST",
      body: JSON.stringify({ action: "start", stage: "stage5" })
    })
    const res = await POST(req, { params: Promise.resolve({ id: "1" }) })
    expect(res.status).toBe(200)

    expect(mockFetch).toHaveBeenCalledWith(
      "http://stages:8002/stage5/run?background=true",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ campaign_id: 1 })
      })
    )
  })
})
