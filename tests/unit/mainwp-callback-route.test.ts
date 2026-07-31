import { describe, it, expect, vi, beforeEach } from "vitest"
import { POST } from "@/app/api/n8n/mainwp-callback/route"
import { NextRequest } from "next/server"

vi.mock("@/lib/db", () => ({
  query: vi.fn(),
}))

import { query } from "@/lib/db"

describe("POST /api/n8n/mainwp-callback", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("returns 400 when body payload fails validation", async () => {
    const req = new NextRequest("http://localhost/api/n8n/mainwp-callback", {
      method: "POST",
      body: JSON.stringify({ token: "" })
    })

    const res = await POST(req)
    const data = await res.json()

    expect(res.status).toBe(400)
    expect(data.error).toBe("Invalid request")
  })

  it("returns 401 when token is not found in database", async () => {
    vi.mocked(query).mockResolvedValueOnce([] as any)

    const req = new NextRequest("http://localhost/api/n8n/mainwp-callback", {
      method: "POST",
      body: JSON.stringify({
        token: "invalid_token_123",
        status: "email_sent"
      })
    })

    const res = await POST(req)
    const data = await res.json()

    expect(res.status).toBe(401)
    expect(data.error).toBe("Invalid or expired token")
  })

  it("updates lead status timestamp and returns 200 on valid token", async () => {
    vi.mocked(query)
      .mockResolvedValueOnce([{ candidate_id: 42 }] as any) // Token lookup
      .mockResolvedValueOnce([] as any) // Update query

    const req = new NextRequest("http://localhost/api/n8n/mainwp-callback", {
      method: "POST",
      body: JSON.stringify({
        token: "valid_token_abc",
        status: "plugin_installed",
        mainwp_site_id: "site_99"
      })
    })

    const res = await POST(req)
    const data = await res.json()

    expect(res.status).toBe(200)
    expect(data.ok).toBe(true)
    expect(query).toHaveBeenLastCalledWith(
      expect.stringContaining("plugin_installed_at = now()"),
      ["site_99", 42]
    )
  })

  it("correctly maps plugin_downloaded to plugin_download_at column", async () => {
    vi.mocked(query)
      .mockResolvedValueOnce([{ candidate_id: 42 }] as any)
      .mockResolvedValueOnce([] as any)

    const req = new NextRequest("http://localhost/api/n8n/mainwp-callback", {
      method: "POST",
      body: JSON.stringify({
        token: "valid_token_abc",
        status: "plugin_downloaded"
      })
    })

    const res = await POST(req)
    expect(res.status).toBe(200)
    expect(query).toHaveBeenLastCalledWith(
      expect.stringContaining("plugin_download_at = now()"),
      [null, 42]
    )
  })
})
