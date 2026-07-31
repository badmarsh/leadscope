import { describe, it, expect } from "vitest"
import { campaigns, campaignUsage, rowToLead } from "../../lib/leads-data"

// ---------------------------------------------------------------------------
// Shared test row factory
// ---------------------------------------------------------------------------
const BASE_ROW = {
  id: 1,
  campaign_id: 1,
  domain: "example.com",
  company_name: "Example Co",
  source: "publicwww",
  created_at: "2026-01-01T00:00:00Z",
  score: 75,
  rationale: "Good fit",
  evidence_urls: ["https://example.com"],
  evidence_data: { evaluator_type: "urls" },
  note: null,
  contact_email: null,
  contact_phone: null,
  contact_name: null,
  screenshot_url: null,
  products_sold: null,
  enrichment_report: null,
  draft_email: null,
  estimated_size: null,
  estimated_revenue: null,
  estimated_traffic: null,
  audit_token: null,
  mainwp_webhook_token: null,
}

function makeRow(overrides: Record<string, unknown> = {}) {
  return { ...BASE_ROW, ...overrides }
}

// ---------------------------------------------------------------------------
// Campaign metadata (keep old assertions)
// ---------------------------------------------------------------------------
describe("lib/leads-data — campaign metadata", () => {
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

// ---------------------------------------------------------------------------
// rowToLead — Status mapping regression tests
// These tests would have caught the dashboard.tsx statusMap bug where
// 'evaluated' and 'enriched' were falling through to the 'pending' fallback.
// ---------------------------------------------------------------------------
describe("rowToLead — DB status → UI status mapping", () => {
  const cases: Array<[string, string]> = [
    ["evaluated",         "evaluated"],
    ["enriched",          "enriched"],
    ["approved",          "approved"],
    ["rejected",          "rejected"],
    ["discarded",         "discarded"],
    ["junk",              "junk"],
    ["new",               "pending"],
    ["evaluating",        "pending"],
    ["pending_review",    "pending"],
    ["enrichment_failed", "enrichment_failed"],
    ["invalid",           "enrichment_failed"],
    ["stale",             "rejected"],
    ["duplicate",         "rejected"],
  ]

  it.each(cases)("DB status '%s' → UI status '%s'", (dbStatus, expectedUiStatus) => {
    const lead = rowToLead(makeRow({ status: dbStatus }))
    expect(lead.status).toBe(expectedUiStatus)
  })

  it("unknown DB status falls back to 'pending' (safe default)", () => {
    const lead = rowToLead(makeRow({ status: "some_future_status_we_dont_know" }))
    expect(lead.status).toBe("pending")
  })

  /**
   * REGRESSION: This exact scenario caused the 'For review' tab to show 0 leads.
   * 'evaluated' must map to 'evaluated', NOT fall through to 'pending'.
   */
  it("REGRESSION: evaluated leads are NOT mapped to pending", () => {
    const lead = rowToLead(makeRow({ status: "evaluated" }))
    expect(lead.status).not.toBe("pending")
    expect(lead.status).toBe("evaluated")
  })

  it("REGRESSION: enriched leads are NOT mapped to pending", () => {
    const lead = rowToLead(makeRow({ status: "enriched" }))
    expect(lead.status).not.toBe("pending")
    expect(lead.status).toBe("enriched")
  })
})

// ---------------------------------------------------------------------------
// rowToLead — Field mapping
// ---------------------------------------------------------------------------
describe("rowToLead — field mapping", () => {
  it("maps id to string", () => {
    const lead = rowToLead(makeRow({ id: 42 }))
    expect(lead.id).toBe("42")
  })

  it("falls back to domain when company_name is null", () => {
    const lead = rowToLead(makeRow({ company_name: null }))
    expect(lead.company).toBe("example.com")
  })

  it("uses company_name when present", () => {
    const lead = rowToLead(makeRow({ company_name: "Acme Corp" }))
    expect(lead.company).toBe("Acme Corp")
  })

  it("maps score from evaluation row", () => {
    const lead = rowToLead(makeRow({ score: 88 }))
    expect(lead.score).toBe(88)
  })

  it("score defaults to 0 when null", () => {
    const lead = rowToLead(makeRow({ score: null }))
    expect(lead.score).toBe(0)
  })

  it("maps contact fields", () => {
    const lead = rowToLead(makeRow({
      contact_email: "a@b.com",
      contact_phone: "+421900000000",
      contact_name: "Jan Novak",
    }))
    expect(lead.contact_email).toBe("a@b.com")
    expect(lead.contact_phone).toBe("+421900000000")
    expect(lead.contact_name).toBe("Jan Novak")
  })

  it("maps null contact fields to undefined", () => {
    const lead = rowToLead(makeRow({ contact_email: null, contact_phone: null }))
    expect(lead.contact_email).toBeUndefined()
    expect(lead.contact_phone).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// rowToLead — Evidence type detection
// ---------------------------------------------------------------------------
describe("rowToLead — evidence detection", () => {
  it("defaults to urls evidence type", () => {
    const lead = rowToLead(makeRow({
      evidence_urls: ["https://example.com/proof"],
      evidence_data: { evaluator_type: "urls" },
    }))
    expect(lead.evidence.kind).toBe("urls")
    expect((lead.evidence as { kind: "urls"; urls: string[] }).urls).toContain("https://example.com/proof")
  })

  it("detects image_quality evaluator type as photos evidence", () => {
    const lead = rowToLead(makeRow({
      evidence_data: {
        evaluator_type: "image_quality",
        images_analyzed: ["https://shop.example.com/img1.jpg"],
      },
    }))
    expect(lead.evidence.kind).toBe("photos")
  })

  it("detects threat_intel evaluator type as malware evidence", () => {
    const lead = rowToLead(makeRow({
      evidence_data: {
        evaluator_type: "threat_intel",
        malware_family: "Emotet",
        source_post_title: "Malware post",
        source_post_url: "https://example.com/post",
        last_confirmed: "2026-01-01",
      },
    }))
    expect(lead.evidence.kind).toBe("malware")
    expect((lead.evidence as { kind: "malware"; malwareFamily: string }).malwareFamily).toBe("Emotet")
  })
})
