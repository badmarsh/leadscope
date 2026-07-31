import { describe, it, expect } from "vitest"
import { rowToLead } from "../../lib/leads-data"

describe("Product-Image Evidence Pipeline End-to-End Contract", () => {
  const baseDbRow = {
    id: 101,
    campaign_id: 2, // shoe-photo campaign
    domain: "boutique-shoes.com",
    company_name: "Boutique Shoes",
    status: "evaluated",
    created_at: "2026-07-31T12:00:00Z",
    score: 85,
    rationale: "High opportunity lead with amateur product photos.",
    evidence_urls: ["https://boutique-shoes.com"],
  }

  it("handles evaluators producing valid product images (has_product_images)", () => {
    const dbRow = {
      ...baseDbRow,
      evidence_data: {
        evaluator_type: "image_quality",
        product_discovery_status: "has_product_images",
        images_analyzed: [
          "https://boutique-shoes.com/images/shoe1.jpg",
          "https://boutique-shoes.com/images/shoe2.jpg",
        ],
        homepage_fallback_images: [],
      },
    }

    const lead = rowToLead(dbRow)

    expect(lead.evidence.kind).toBe("photos")
    if (lead.evidence.kind === "photos") {
      expect(lead.evidence.photos.length).toBe(2)
      expect(lead.evidence.photos[0].label).toBe("Product Image 1")
      expect(lead.evidence.photos[0].src).toBe("https://boutique-shoes.com/images/shoe1.jpg")
      expect(lead.evidence.photos[1].label).toBe("Product Image 2")
      expect(lead.evidence.photos[1].src).toBe("https://boutique-shoes.com/images/shoe2.jpg")
    }
  })

  it("handles Stage 5 fallback images when evaluator finds zero product images (fallback_used)", () => {
    const dbRow = {
      ...baseDbRow,
      evidence_data: {
        evaluator_type: "image_quality",
        product_discovery_status: "fallback_used",
        images_analyzed: [],
        homepage_fallback_images: [
          "https://boutique-shoes.com/assets/hero_banner.jpg",
          "https://boutique-shoes.com/assets/storefront.jpg",
        ],
      },
    }

    const lead = rowToLead(dbRow)

    expect(lead.evidence.kind).toBe("photos")
    if (lead.evidence.kind === "photos") {
      expect(lead.evidence.photos.length).toBe(2)
      expect(lead.evidence.photos[0].label).toBe("Homepage Image 1")
      expect(lead.evidence.photos[0].src).toBe("https://boutique-shoes.com/assets/hero_banner.jpg")
      expect(lead.evidence.photos[1].label).toBe("Homepage Image 2")
      expect(lead.evidence.photos[1].src).toBe("https://boutique-shoes.com/assets/storefront.jpg")
    }
  })

  it("falls back to URL evidence when both product images and fallback images are absent", () => {
    const dbRow = {
      ...baseDbRow,
      evidence_data: {
        evaluator_type: "urls",
        images_analyzed: [],
        homepage_fallback_images: [],
      },
    }

    const lead = rowToLead(dbRow)

    expect(lead.evidence.kind).toBe("urls")
    if (lead.evidence.kind === "urls") {
      expect(lead.evidence.urls).toEqual(["https://boutique-shoes.com"])
    }
  })
})
