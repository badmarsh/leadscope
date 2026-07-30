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
}))

import { getIronSession } from "iron-session"
import { query } from "@/lib/db"
import { POST } from "@/app/api/leads/export/crm/route"

describe("POST /api/leads/export/crm", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal("fetch", vi.fn())
  })

  it("returns 401 when unauthorized", async () => {
    vi.mocked(getIronSession).mockResolvedValue({ loggedIn: false } as any)
    const req = new NextRequest("http://localhost/api/leads/export/crm", {
      method: "POST",
      body: JSON.stringify({ campaign_id: 1, webhook_url: "https://crm.com/hook" }),
    })
    const res = await POST(req)
    expect(res.status).toBe(401)
  })

  it("returns 400 when missing required fields", async () => {
    vi.mocked(getIronSession).mockResolvedValue({ loggedIn: true } as any)
    const req = new NextRequest("http://localhost/api/leads/export/crm", {
      method: "POST",
      body: JSON.stringify({ campaign_id: 1 }),
    })
    const res = await POST(req)
    expect(res.status).toBe(400)
  })

  it("returns 400 when webhook_url is not HTTPS", async () => {
    vi.mocked(getIronSession).mockResolvedValue({ loggedIn: true } as any)
    const req = new NextRequest("http://localhost/api/leads/export/crm", {
      method: "POST",
      body: JSON.stringify({ campaign_id: 1, webhook_url: "http://insecure.com/hook" }),
    })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error).toContain("must be a valid HTTPS URL")
  })

  it("delivers approved leads payload to CRM webhook", async () => {
    vi.mocked(getIronSession).mockResolvedValue({ loggedIn: true } as any)
    vi.mocked(query).mockResolvedValue([
      {
        domain: "lead.com",
        company_name: "Lead Co",
        contact_email: "boss@lead.com",
        contact_name: "Jane Boss",
        contact_phone: "123456",
        score: 85,
        enrichment_report: "Report",
        products_sold: ["Shoes"],
      },
    ] as any)

    vi.mocked(fetch).mockResolvedValue({ ok: true, status: 200 } as any)

    const req = new NextRequest("http://localhost/api/leads/export/crm", {
      method: "POST",
      body: JSON.stringify({ campaign_id: 1, webhook_url: "https://hooks.zapier.com/test" }),
    })
    const res = await POST(req)
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.ok).toBe(true)
    expect(body.exported).toBe(1)

    expect(vi.mocked(fetch).mock.calls[0][0].toString()).toContain("zapier.com")
  })
})
