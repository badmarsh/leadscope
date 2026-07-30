import { describe, it, expect, vi, beforeEach } from "vitest"
import { GET } from "@/app/api/logs/route"

vi.mock("iron-session", () => ({
  getIronSession: vi.fn(),
}))

vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({}),
}))

vi.mock("fs/promises", () => ({
  default: {
    stat: vi.fn(),
    open: vi.fn(),
  },
}))

import { getIronSession } from "iron-session"
import fs from "fs/promises"

describe("GET /api/logs", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("returns 401 when unauthorized", async () => {
    vi.mocked(getIronSession).mockResolvedValue({ loggedIn: false } as any)
    const res = await GET()
    expect(res.status).toBe(401)
  })

  it("returns fallback message when log file stat fails", async () => {
    vi.mocked(getIronSession).mockResolvedValue({ loggedIn: true } as any)
    vi.mocked(fs.stat).mockRejectedValue(new Error("File not found"))

    const res = await GET()
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.logs).toBe("Logs not initialized yet...")
  })

  it("reads log file content when file exists", async () => {
    vi.mocked(getIronSession).mockResolvedValue({ loggedIn: true } as any)
    vi.mocked(fs.stat).mockResolvedValue({ size: 100 } as any)

    const mockFd = {
      read: vi.fn().mockImplementation(async (buffer: Buffer) => {
        buffer.write("First line\nSecond line log content")
        return { bytesRead: 100 }
      }),
      close: vi.fn().mockResolvedValue(undefined),
    }
    vi.mocked(fs.open).mockResolvedValue(mockFd as any)

    const res = await GET()
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.logs).toContain("Second line log content")
  })
})
