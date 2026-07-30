import { describe, it, expect, vi, beforeEach } from "vitest"
import { NextRequest } from "next/server"

vi.mock("@/lib/db", () => ({
  query: vi.fn(),
}))

import { query } from "@/lib/db"
import { GET, POST, DELETE } from "@/app/api/campaigns/[id]/dnc/route"

describe("/api/campaigns/[id]/dnc", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("returns 400 for invalid campaign ID on GET", async () => {
    const req = new NextRequest("http://localhost/api/campaigns/abc/dnc")
    const res = await GET(req, { params: Promise.resolve({ id: "abc" }) })
    expect(res.status).toBe(400)
  })

  it("returns exclusion list on GET", async () => {
    vi.mocked(query).mockResolvedValue([
      { id: 1, domain: "blocked.com", reason: "Spam", added_at: "2026-01-01" },
    ] as any)
    const req = new NextRequest("http://localhost/api/campaigns/1/dnc")
    const res = await GET(req, { params: Promise.resolve({ id: "1" }) })
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data.exclusions).toHaveLength(1)
    expect(data.exclusions[0].domain).toBe("blocked.com")
  })

  it("inserts new exclusion on POST", async () => {
    vi.mocked(query).mockResolvedValue([
      { id: 2, domain: "new-block.com", campaign_id: 1, reason: "Manual" },
    ] as any)
    const req = new NextRequest("http://localhost/api/campaigns/1/dnc", {
      method: "POST",
      body: JSON.stringify({ domain: "new-block.com", reason: "Manual" }),
    })
    const res = await POST(req, { params: Promise.resolve({ id: "1" }) })
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data.exclusion.domain).toBe("new-block.com")
  })

  it("returns 400 when domain missing on POST", async () => {
    const req = new NextRequest("http://localhost/api/campaigns/1/dnc", {
      method: "POST",
      body: JSON.stringify({ reason: "No domain" }),
    })
    const res = await POST(req, { params: Promise.resolve({ id: "1" }) })
    expect(res.status).toBe(400)
  })

  it("deletes exclusion on DELETE", async () => {
    vi.mocked(query).mockResolvedValue([] as any)
    const req = new NextRequest("http://localhost/api/campaigns/1/dnc?id=5", {
      method: "DELETE",
    })
    const res = await DELETE(req, { params: Promise.resolve({ id: "1" }) })
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data.success).toBe(true)
  })
})
