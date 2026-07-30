import { describe, it, expect, vi, beforeEach } from "vitest"
import { GET } from "@/app/api/admin/health/route"

vi.mock("@/lib/db", () => ({
  query: vi.fn(),
}))

import { query } from "@/lib/db"

describe("/api/admin/health", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("returns system health metrics on GET", async () => {
    vi.mocked(query)
      .mockResolvedValueOnce([
        { id: 1, slug: "wp-remediation", stage1_status: "idle", stage2_status: "running", stage3_status: "idle", stage5_status: "idle" },
      ] as any) // campaigns
      .mockResolvedValueOnce([
        { status: "approved", count: "10" },
        { status: "discarded", count: "5" },
      ] as any) // statusCounts
      .mockResolvedValueOnce([
        { cost_today: "1.25", cost_week: "15.50" },
      ] as any) // costAggregates
      .mockResolvedValueOnce([
        { count: "2" },
      ] as any) // stuckCandidates

    const res = await GET()
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.ok).toBe(true)
    expect(body.data.statusCounts.approved).toBe(10)
    expect(body.data.cost.today).toBe(1.25)
    expect(body.data.cost.week).toBe(15.50)
    expect(body.data.stuckEnrichments).toBe(2)
  })

  it("returns 500 when database error occurs", async () => {
    vi.mocked(query).mockRejectedValue(new Error("DB connection lost"))
    const res = await GET()
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.ok).toBe(false)
    expect(body.error).toBe("Internal server error")
  })
})
