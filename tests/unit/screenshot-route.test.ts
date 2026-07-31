import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import dns from "dns"
import { NextRequest } from "next/server"
import { GET } from "../../app/api/screenshot/route"

const mockGetIronSession = vi.fn()
vi.mock("iron-session", () => ({ getIronSession: (...args: any[]) => mockGetIronSession(...args) }))
vi.mock("next/headers", () => ({ cookies: () => Promise.resolve({}) }))

// Mock global fetch
const mockFetch = vi.fn()
vi.stubGlobal("fetch", mockFetch)

describe("GET /api/screenshot", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetIronSession.mockResolvedValue({ loggedIn: true })
    
    // Default DNS mock behavior to return safe IPs
    vi.spyOn(dns.promises, 'lookup').mockImplementation(async (hostname) => {
      // Mock some safe responses
      if (hostname === 'safe-site.com' || hostname === 'safe.com') {
        return [{ address: '8.8.8.8', family: 4 }] as any
      }
      return [{ address: '1.2.3.4', family: 4 }] as any
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("returns 401 when not authenticated", async () => {
    mockGetIronSession.mockResolvedValue({ loggedIn: false })
    const req = new NextRequest("http://localhost/api/screenshot?url=https://example.com")
    const res = await GET(req)
    expect(res.status).toBe(401)
  })

  it("returns 400 when url param is missing", async () => {
    const req = new NextRequest("http://localhost/api/screenshot")
    const res = await GET(req)
    expect(res.status).toBe(400)
  })

  // SSRF protection tests
  it.each([
    "http://localhost/secret",
    "http://127.0.0.1/etc/passwd",
    "http://10.0.0.1/internal",
    "http://192.168.1.100/router",
    "http://169.254.169.254/metadata",
  ])("blocks SSRF attempt: %s", async (blockedUrl) => {
    const req = new NextRequest(`http://localhost/api/screenshot?url=${encodeURIComponent(blockedUrl)}`)
    const res = await GET(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error).toMatch(/invalid|disallowed/i)
  })

  it("prevents DNS rebinding TOCTOU via IP pinning", async () => {
    const fakeJpeg = Buffer.from([0xFF, 0xD8, 0xFF])
    mockFetch.mockResolvedValue({
      ok: true,
      arrayBuffer: async () => fakeJpeg.buffer,
    })
    
    let lookupCount = 0
    vi.spyOn(dns.promises, 'lookup').mockImplementation(async () => {
      lookupCount++
      if (lookupCount === 1) {
        return [{ address: '8.8.8.8', family: 4 }] as any // Public IP on check
      }
      return [{ address: '127.0.0.1', family: 4 }] as any // Private IP on fetch
    })

    const req = new NextRequest("http://localhost/api/screenshot?url=https://attacker-rebind.com")
    const res = await GET(req)
    
    expect(res.status).toBe(200)
    
    // The fetch should use the pinned public IP from the first lookup
    const fetchPayload = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(fetchPayload.url).toBe("https://8.8.8.8/")
    // And it should preserve the original hostname in headers
    expect(fetchPayload.setExtraHTTPHeaders.Host).toBe("attacker-rebind.com")
  })

  it("blocks non-http protocols", async () => {
    const req = new NextRequest("http://localhost/api/screenshot?url=file:///etc/passwd")
    const res = await GET(req)
    expect(res.status).toBe(400)
  })

  it("forwards valid URL to browserless and returns jpeg", async () => {
    const fakeJpeg = Buffer.from([0xFF, 0xD8, 0xFF])
    mockFetch.mockResolvedValue({
      ok: true,
      arrayBuffer: async () => fakeJpeg.buffer,
    })
    const req = new NextRequest("http://localhost/api/screenshot?url=https://safe-site.com")
    const res = await GET(req)
    expect(res.status).toBe(200)
    expect(res.headers.get("Content-Type")).toBe("image/jpeg")
  })

  it("sends GDPR removal script and domcontentloaded in request body", async () => {
    const fakeJpeg = Buffer.from([0xFF, 0xD8])
    mockFetch.mockResolvedValue({ ok: true, arrayBuffer: async () => fakeJpeg.buffer })
    const req = new NextRequest("http://localhost/api/screenshot?url=https://safe.com")
    await GET(req)
    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.gotoOptions.waitUntil).toBe("domcontentloaded")
    expect(body.evaluate).toContain("cookie")
    expect(body.evaluate).toContain("gdpr")
  })

  it("returns 502 when browserless returns 5xx", async () => {
    const consoleSpy = vi.spyOn(console, "warn").mockImplementation(() => {})
    mockFetch.mockResolvedValue({ ok: false, status: 503, statusText: "Service Unavailable" })
    const req = new NextRequest("http://localhost/api/screenshot?url=https://safe.com")
    const res = await GET(req)
    expect(res.status).toBe(502)
    consoleSpy.mockRestore()
  })

  it("returns Cache-Control header on success", async () => {
    mockFetch.mockResolvedValue({ ok: true, arrayBuffer: async () => Buffer.from([0xFF]).buffer })
    const req = new NextRequest("http://localhost/api/screenshot?url=https://safe.com")
    const res = await GET(req)
    expect(res.headers.get("Cache-Control")).toContain("max-age=86400")
  })
})
