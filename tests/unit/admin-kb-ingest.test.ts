import { describe, it, expect, vi, beforeEach } from "vitest"
import { POST } from "../../app/api/admin/kb-ingest/route"

const mockGetIronSession = vi.fn()
vi.mock("iron-session", () => ({
  getIronSession: (...args: any[]) => mockGetIronSession(...args)
}))

vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({})
}))

const mockFetch = vi.fn()
vi.stubGlobal("fetch", mockFetch)

describe("POST /api/admin/kb-ingest", () => {
  const originalEnv = process.env

  beforeEach(() => {
    vi.clearAllMocks()
    process.env = { ...originalEnv, INTERNAL_API_TOKEN: "secret_token" }
    mockGetIronSession.mockResolvedValue({ loggedIn: true })
  })

  it("returns 401 when unauthorized", async () => {
    mockGetIronSession.mockResolvedValue({ loggedIn: false })
    const res = await POST()
    expect(res.status).toBe(401)
  })

  it("returns 500 when INTERNAL_API_TOKEN is missing", async () => {
    delete process.env.INTERNAL_API_TOKEN
    const res = await POST()
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error).toContain("missing internal API token")
  })

  it("forwards request to stages service and returns response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: "ok", message: "KB ingestion triggered" })
    })

    const res = await POST()
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.message).toBe("KB ingestion triggered")

    expect(mockFetch).toHaveBeenCalledWith(
      "http://stages:8002/kb/ingest?background=true",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-Internal-Token": "secret_token" })
      })
    )
  })

  it("returns 500 when fetch throws an error", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {})
    mockFetch.mockRejectedValueOnce(new Error("Connection refused"))

    const res = await POST()
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error).toContain("Connection refused")
    consoleSpy.mockRestore()
  })
})
