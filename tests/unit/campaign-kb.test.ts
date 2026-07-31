import { describe, it, expect, vi, beforeEach } from "vitest"
import { NextRequest } from "next/server"
import { GET, POST, PUT, DELETE } from "../../app/api/campaigns/[id]/kb/route"

const mockQuery = vi.fn()
vi.mock("@/lib/db", () => ({
  query: (...args: any[]) => mockQuery(...args)
}))

const mockGetIronSession = vi.fn()
vi.mock("iron-session", () => ({
  getIronSession: (...args: any[]) => mockGetIronSession(...args)
}))

vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({})
}))

describe("/api/campaigns/[id]/kb", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetIronSession.mockResolvedValue({ loggedIn: true })
  })

  describe("GET", () => {
    it("returns 401 when unauthorized", async () => {
      mockGetIronSession.mockResolvedValue({ loggedIn: false })
      const req = new NextRequest("http://localhost/api/campaigns/1/kb")
      const res = await GET(req, { params: Promise.resolve({ id: "1" }) })
      expect(res.status).toBe(401)
    })

    it("returns signatures for campaign", async () => {
      mockQuery.mockResolvedValueOnce([{ id: 10, snippet: "eval(base64)", malware_family: "wp_eval" }])
      const req = new NextRequest("http://localhost/api/campaigns/1/kb")
      const res = await GET(req, { params: Promise.resolve({ id: "1" }) })
      expect(res.status).toBe(200)
      const body = await res.json()
      expect(body.signatures).toHaveLength(1)
      expect(body.signatures[0].malware_family).toBe("wp_eval")
    })
  })

  describe("POST", () => {
    it("returns 400 when snippet is missing", async () => {
      const req = new NextRequest("http://localhost/api/campaigns/1/kb", {
        method: "POST",
        body: JSON.stringify({ malware_family: "wp_eval" })
      })
      const res = await POST(req, { params: Promise.resolve({ id: "1" }) })
      expect(res.status).toBe(400)
    })

    it("creates a new malware signature", async () => {
      mockQuery.mockResolvedValueOnce([{ id: 12, snippet: "shell_exec", malware_family: "webshell" }])
      const req = new NextRequest("http://localhost/api/campaigns/1/kb", {
        method: "POST",
        body: JSON.stringify({ snippet: "shell_exec", malware_family: "webshell" })
      })
      const res = await POST(req, { params: Promise.resolve({ id: "1" }) })
      expect(res.status).toBe(200)
      const body = await res.json()
      expect(body.signature.id).toBe(12)
    })

    it("returns 400 when signature already exists", async () => {
      const duplicateErr = new Error("Duplicate")
      ;(duplicateErr as any).code = "23505"
      mockQuery.mockRejectedValueOnce(duplicateErr)

      const req = new NextRequest("http://localhost/api/campaigns/1/kb", {
        method: "POST",
        body: JSON.stringify({ snippet: "shell_exec" })
      })
      const res = await POST(req, { params: Promise.resolve({ id: "1" }) })
      expect(res.status).toBe(400)
      const body = await res.json()
      expect(body.error).toContain("already exists")
    })
  })

  describe("PUT", () => {
    it("updates existing signature", async () => {
      mockQuery.mockResolvedValueOnce([{ id: 5, snippet: "updated_snippet" }])
      const req = new NextRequest("http://localhost/api/campaigns/1/kb", {
        method: "PUT",
        body: JSON.stringify({ id: 5, snippet: "updated_snippet" })
      })
      const res = await PUT(req, { params: Promise.resolve({ id: "1" }) })
      expect(res.status).toBe(200)
    })
  })

  describe("DELETE", () => {
    it("deletes signature by sig_id", async () => {
      mockQuery.mockResolvedValueOnce([])
      const req = new NextRequest("http://localhost/api/campaigns/1/kb?sig_id=5")
      const res = await DELETE(req, { params: Promise.resolve({ id: "1" }) })
      expect(res.status).toBe(200)
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("DELETE FROM malware_signatures"),
        ["5", "1"]
      )
    })
  })
})
