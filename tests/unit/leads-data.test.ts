import { describe, it, expect } from "vitest"
import { campaigns, campaignUsage } from "../../lib/leads-data"

describe("lib/leads-data", () => {
  it("defines active campaigns with correct ids", () => {
    expect(campaigns).toBeDefined()
    expect(campaigns.length).toBeGreaterThan(0)
    const ids = campaigns.map(c => c.id)
    expect(ids).toContain("jenex")
    expect(ids).toContain("shoe-photo")
    expect(ids).toContain("wp-remediation")
  })

  it("contains usage statistics for each campaign", () => {
    expect(campaignUsage.jenex).toBeDefined()
    expect(campaignUsage["shoe-photo"]).toBeDefined()
    expect(campaignUsage["wp-remediation"]).toBeDefined()
    expect(campaignUsage.jenex.openRouterSpend).toMatch(/^\$\d+\.\d{2}$/)
  })
})
