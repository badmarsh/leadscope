// MOCK DATA — replaced in Part 4b of the coding-agent build
// Real data comes from GET /api/leads?campaign_id=X (FastAPI backend)
// See leadgen-platform-coding-agent-megaprompt.md §Part 4b for wiring instructions

export type CampaignId = "jenex" | "shoe-photo" | "wp-remediation"

export type LeadStatus = "pending" | "approved" | "rejected" | "enrichment_failed" | "junk"

export type CampaignStatus = "active" | "paused" | "draft"

export interface Campaign {
  id: CampaignId
  name: string
  shortName: string
  status: CampaignStatus
}

export interface JenexEvidence {
  kind: "urls"
  urls: string[]
}

export interface ShoeEvidence {
  kind: "photos"
  photos: { src: string; label: string }[]
}

export interface WpEvidence {
  kind: "malware"
  malwareFamily: string
  sourcePost: { title: string; url: string }
  lastConfirmed: string
}

export type Evidence = JenexEvidence | ShoeEvidence | WpEvidence

export interface PhaseXProof {
  proof_type: "google_serp_spam" | "cloaked_redirect"
  evidence_text: string
  indexed_spam_pages?: number
  example_url?: string
  example_title?: string
  example_snippet?: string
  redirect_destination?: string
  network_trace?: string[]
}

export interface PhaseXExposure {
  critical_found: boolean
  exposures: Array<{ url: string; severity: string; snippet?: string }>
}

export interface Lead {
  id: string
  campaignId: CampaignId
  company: string
  domain: string
  score: number
  status: LeadStatus
  dateFound: string
  rationale: string
  evidence: Evidence
  evidence_data?: Record<string, unknown>
  note?: string
  contact_email?: string
  contact_phone?: string
  contact_name?: string
  screenshot_url?: string
  products_sold?: string[]
  enrichment_report?: string
  draft_email?: string
  estimated_size?: string
  estimated_revenue?: string
  estimated_traffic?: string
  // Phase X fields
  audit_token?: string
  mainwp_webhook_token?: string
  proof_data?: PhaseXProof | null
  exposure_scan?: PhaseXExposure | null
  processing_generation?: number
  enrichment_attempt_count?: number
}

export interface CampaignUsage {
  openRouterSpend: string
  publicWwwUsed: number
  publicWwwLimit: number
}

export const campaigns: Campaign[] = [
  { id: "jenex", name: "JENEX HVAC Hungary", shortName: "JENEX", status: "active" },
  { id: "shoe-photo", name: "Shoe Photo Upgrade", shortName: "Shoes", status: "active" },
  { id: "wp-remediation", name: "WP Malware Remediation", shortName: "WP Remediation", status: "active" },
]

export const campaignUsage: Record<CampaignId, CampaignUsage> = {
  jenex: { openRouterSpend: "$4.20", publicWwwUsed: 340, publicWwwLimit: 1000 },
  "shoe-photo": { openRouterSpend: "$2.87", publicWwwUsed: 112, publicWwwLimit: 1000 },
  "wp-remediation": { openRouterSpend: "$6.15", publicWwwUsed: 583, publicWwwLimit: 1000 },
}

export const leads: Lead[] = [
  // ── JENEX HVAC (Hungary) ──────────────────────────────────────────
  {
    id: "jx-001",
    campaignId: "jenex",
    company: "Budapesti Klíma Kft.",
    domain: "budapestiklima.hu",
    score: 92,
    status: "pending",
    dateFound: "2026-07-14",
    rationale:
      "Mid-size HVAC installer in Budapest with 25+ employees per their team page. Currently lists Daikin and Mitsubishi as partners but no premium residential heat-pump line. Multiple service pages mention supply delays with their current distributor. Strong fit for JENEX distribution partnership.",
    evidence: {
      kind: "urls",
      urls: [
        "https://budapestiklima.hu/rolunk",
        "https://budapestiklima.hu/partnereink",
        "https://budapestiklima.hu/blog/keszlethiany-2026",
      ],
    },
  },
  {
    id: "jx-002",
    campaignId: "jenex",
    company: "Pannon Hűtéstechnika",
    domain: "pannonhutes.hu",
    score: 85,
    status: "pending",
    dateFound: "2026-07-13",
    rationale:
      "Regional refrigeration and climate contractor covering Transdanubia. Recent job postings indicate expansion into residential AC installs. No exclusive brand tie-in detected on site; pricing page suggests they source ad hoc from wholesalers.",
    evidence: {
      kind: "urls",
      urls: ["https://pannonhutes.hu/szolgaltatasok", "https://pannonhutes.hu/karrier"],
    },
  },
  {
    id: "jx-003",
    campaignId: "jenex",
    company: "Alföld Klíma és Fűtés",
    domain: "alfoldklima.hu",
    score: 71,
    status: "pending",
    dateFound: "2026-07-12",
    rationale:
      "Smaller installer in Szeged, roughly 8 employees. Active on tenders portal for public building retrofits — heat-pump demand likely. Site mentions interest in new supplier relationships on their contact page.",
    evidence: {
      kind: "urls",
      urls: [
        "https://alfoldklima.hu/kapcsolat",
        "https://alfoldklima.hu/referenciak",
        "https://kozbeszerzes.hu/tender/2026-0412",
      ],
    },
  },
  {
    id: "jx-004",
    campaignId: "jenex",
    company: "Duna Épületgépészet Zrt.",
    domain: "dunaepgep.hu",
    score: 64,
    status: "approved",
    dateFound: "2026-07-10",
    rationale:
      "Large building-services firm; HVAC is one of four divisions. Already carries two competing brands, but their scale makes even a secondary line worthwhile. Approved for outreach with the enterprise pitch variant.",
    evidence: {
      kind: "urls",
      urls: ["https://dunaepgep.hu/divizio/hvac"],
    },
    note: "Use enterprise pitch — they won't drop existing brands.",
  },
  {
    id: "jx-005",
    campaignId: "jenex",
    company: "Zöld Otthon Klíma Bt.",
    domain: "zoldotthonklima.hu",
    score: 38,
    status: "rejected",
    dateFound: "2026-07-09",
    rationale:
      "Two-person operation focused on maintenance rather than installs. Revenue likely below distribution-partner threshold. Site last updated 2024.",
    evidence: {
      kind: "urls",
      urls: ["https://zoldotthonklima.hu"],
    },
    note: "Too small. Revisit if they post install jobs.",
  },
  {
    id: "jx-006",
    campaignId: "jenex",
    company: "Kelet-Magyar Hőtechnika",
    domain: "keletmagyarho.hu",
    score: 0,
    status: "enrichment_failed",
    dateFound: "2026-07-14",
    rationale:
      "Enrichment failed: site returned 403 for all crawler user agents. Company appears in the PublicWWW result set for Daikin partner widgets, but no page content could be retrieved for scoring.",
    evidence: {
      kind: "urls",
      urls: ["https://keletmagyarho.hu"],
    },
  },

  // ── Shoe Photo Upgrade ────────────────────────────────────────────
  {
    id: "sp-001",
    campaignId: "shoe-photo",
    company: "Harlow & Sons Footwear",
    domain: "harlowandsons.com",
    score: 88,
    status: "pending",
    dateFound: "2026-07-15",
    rationale:
      "Independent Shopify store selling premium leather shoes at $180–320 price points, but product photography is phone-quality with cluttered backgrounds and harsh flash. High price-to-photo-quality mismatch — strong candidate for a photo upgrade pitch.",
    evidence: {
      kind: "photos",
      photos: [
        { src: "/shoes/shoe-1.png", label: "PDP hero — brown derby" },
        { src: "/shoes/shoe-4.png", label: "PDP hero — ankle boot" },
      ],
    },
  },
  {
    id: "sp-002",
    campaignId: "shoe-photo",
    company: "Stride Culture",
    domain: "strideculture.co",
    score: 76,
    status: "pending",
    dateFound: "2026-07-14",
    rationale:
      "Sneaker boutique with ~140 SKUs. Roughly a third of listings use supplier stock photos, the rest are amateur shots on carpet with poor white balance. Store runs paid Meta ads, so image quality directly impacts ROAS — good hook for outreach.",
    evidence: {
      kind: "photos",
      photos: [
        { src: "/shoes/shoe-2.png", label: "Listing — white low-top" },
        { src: "/shoes/shoe-3.png", label: "Listing — red runner" },
      ],
    },
  },
  {
    id: "sp-003",
    campaignId: "shoe-photo",
    company: "Bootline Outfitters",
    domain: "bootlineoutfitters.com",
    score: 59,
    status: "pending",
    dateFound: "2026-07-12",
    rationale:
      "Work-boot retailer with mixed photo quality. Top sellers have decent photos, long tail is poor. Mid-priority: pitch may land better as a partial-catalog refresh.",
    evidence: {
      kind: "photos",
      photos: [{ src: "/shoes/shoe-4.png", label: "Long-tail listing — boot" }],
    },
  },
  {
    id: "sp-004",
    campaignId: "shoe-photo",
    company: "Velvet Step",
    domain: "velvetstep.shop",
    score: 81,
    status: "approved",
    dateFound: "2026-07-11",
    rationale:
      "Women's dress-shoe store, high AOV, entirely amateur photography shot at home. Instagram presence suggests owner cares about aesthetics — likely receptive.",
    evidence: {
      kind: "photos",
      photos: [
        { src: "/shoes/shoe-3.png", label: "PDP — heeled sandal listing" },
        { src: "/shoes/shoe-2.png", label: "PDP — flats listing" },
      ],
    },
    note: "Mention their IG — it's much better than the store photos.",
  },
  {
    id: "sp-005",
    campaignId: "shoe-photo",
    company: "KixDeck",
    domain: "kixdeck.io",
    score: 0,
    status: "enrichment_failed",
    dateFound: "2026-07-15",
    rationale:
      "Enrichment failed: product image scraper hit a Cloudflare challenge on every PDP. Store detected via PublicWWW Shopify-theme fingerprint, but no photos could be pulled for quality scoring.",
    evidence: {
      kind: "photos",
      photos: [],
    },
  },

  // ── WP Remediation ────────────────────────────────────────────────
  {
    id: "wp-001",
    campaignId: "wp-remediation",
    company: "Coastal Realty Group",
    domain: "coastalrealtygrp.com",
    score: 95,
    status: "pending",
    dateFound: "2026-07-15",
    rationale:
      "WordPress site actively serving the SocGholish fake-browser-update payload to visitors, confirmed by two independent scans. Business is a mid-size realty firm — reputational risk and lead-gen dependence make this a high-urgency remediation prospect.",
    evidence: {
      kind: "malware",
      malwareFamily: "SocGholish",
      sourcePost: {
        title: "SocGholish resurgence across outdated WP themes — July 2026",
        url: "https://blog.sucuri.net/2026/07/socgholish-resurgence-wp-themes",
      },
      lastConfirmed: "2026-07-15T09:42:00Z",
    },
  },
  {
    id: "wp-002",
    campaignId: "wp-remediation",
    company: "Miller & Frank Dental",
    domain: "millerfrankdental.com",
    score: 83,
    status: "pending",
    dateFound: "2026-07-14",
    rationale:
      "Dental practice site injected with Balada Injector redirect chains via a vulnerable tagDiv theme component. Patients booking online are being redirected intermittently. Practice has 3 locations — plausible budget for cleanup + retainer.",
    evidence: {
      kind: "malware",
      malwareFamily: "Balada Injector",
      sourcePost: {
        title: "Balada Injector exploiting tagDiv Composer, 17k sites affected",
        url: "https://blog.wordfence.com/2026/07/balada-tagdiv-composer",
      },
      lastConfirmed: "2026-07-14T22:10:00Z",
    },
  },
  {
    id: "wp-003",
    campaignId: "wp-remediation",
    company: "Peak Performance Physio",
    domain: "peakperformphysio.com",
    score: 67,
    status: "pending",
    dateFound: "2026-07-13",
    rationale:
      "Site flagged for Sign1 malware serving popup redirects to visitors from search. Injection present in a custom plugin. Smaller business, but active Google Ads spend means the blocklisting risk is a strong urgency lever.",
    evidence: {
      kind: "malware",
      malwareFamily: "Sign1",
      sourcePost: {
        title: "Sign1 campaign tops 40,000 infected WordPress sites",
        url: "https://blog.sucuri.net/2026/06/sign1-campaign-40k-sites",
      },
      lastConfirmed: "2026-07-13T15:27:00Z",
    },
  },
  {
    id: "wp-004",
    campaignId: "wp-remediation",
    company: "Lakeside Wedding Venue",
    domain: "lakesideweddings.net",
    score: 44,
    status: "rejected",
    dateFound: "2026-07-11",
    rationale:
      "Infection confirmed (VexTrio TDS), but the site appears abandoned — no bookings page updates since 2024 and the business's socials point to a new domain. Low likelihood of paying for remediation on a dead property.",
    evidence: {
      kind: "malware",
      malwareFamily: "VexTrio TDS",
      sourcePost: {
        title: "VexTrio: the massive TDS operation routing WP traffic",
        url: "https://blog.malwarebytes.com/2026/05/vextrio-tds-wordpress",
      },
      lastConfirmed: "2026-07-11T08:03:00Z",
    },
    note: "Business moved domains. Dead end.",
  },
  {
    id: "wp-005",
    campaignId: "wp-remediation",
    company: "TrueNorth Accounting",
    domain: "truenorthacct.ca",
    score: 0,
    status: "enrichment_failed",
    dateFound: "2026-07-15",
    rationale:
      "Enrichment failed: WHOIS and contact scraping returned no usable business contact, and the site's contact form is itself broken (500 on submit). Infection signal (SocGholish) remains unverified beyond the initial blog-post IOC match.",
    evidence: {
      kind: "malware",
      malwareFamily: "SocGholish",
      sourcePost: {
        title: "SocGholish resurgence across outdated WP themes — July 2026",
        url: "https://blog.sucuri.net/2026/07/socgholish-resurgence-wp-themes",
      },
      lastConfirmed: "2026-07-12T11:55:00Z",
    },
  },
]

import { DB_ID_TO_CAMPAIGN } from "@/lib/campaigns"

// Map DB row → Lead shape expected by components
export function rowToLead(row: Record<string, unknown>): Lead {
  const evidenceData = (row.evidence_data as Record<string, unknown> | null) ?? {}
  const evaluatorType = (evidenceData.evaluator_type as string | undefined) ?? "urls"

  let evidence: Lead["evidence"]

  if (evaluatorType === "image_quality" || evidenceData.images_analyzed) {
    const rawImages = (evidenceData.images_analyzed as string[] | undefined) ?? []
    const httpImages = rawImages.filter((img) => typeof img === "string" && img.startsWith("http"))
    evidence = {
      kind: "photos",
      photos: httpImages.slice(0, 8).map((src, idx) => ({ 
        src, 
        label: `Product Image ${idx + 1}`
      })),
    }
  } else if (
    evaluatorType === "threat_intel" ||
    evidenceData.malware_family
  ) {
    evidence = {
      kind: "malware",
      malwareFamily: (evidenceData.malware_family as string) ?? "Unknown",
      sourcePost: {
        title: (evidenceData.source_post_title as string) ?? "Security intelligence source",
        url: (evidenceData.source_post_url as string) ?? "#",
      },
      lastConfirmed: (evidenceData.last_confirmed as string) ?? row.created_at,
    }
  } else {
    evidence = {
      kind: "urls",
      urls: (row.evidence_urls as string[] | undefined) ?? [],
    }
  }

  const statusMap: Record<string, Lead["status"]> = {
    pending_review: "pending",
    approved: "approved",
    rejected: "rejected",
    enrichment_failed: "enrichment_failed",
  }

  const dbCampaignId = row.campaign_id as number
  const campaignId: CampaignId = DB_ID_TO_CAMPAIGN[dbCampaignId] ?? "jenex"

  return {
    id: String(row.id),
    campaignId,
    company: (row.company_name as string) ?? (row.domain as string),
    domain: row.domain as string,
    score: (row.score as number) ?? 0,
    status: statusMap[row.status as string] ?? "pending",
    dateFound: new Date(row.created_at as string).toLocaleDateString("en-CA"),
    rationale: (row.rationale as string) ?? "",
    evidence,
    note: (row.note as string) ?? undefined,
    contact_email: (row.contact_email as string) ?? undefined,
    contact_phone: (row.contact_phone as string) ?? undefined,
    contact_name: (row.contact_name as string) ?? undefined,
    screenshot_url: (row.screenshot_url as string) ?? undefined,
    products_sold: (row.products_sold as string[]) ?? undefined,
    enrichment_report: (row.enrichment_report as string) ?? undefined,
    draft_email: (row.draft_email as string) ?? undefined,
    estimated_size: (row.estimated_size as string) ?? undefined,
    estimated_revenue: (row.estimated_revenue as string) ?? undefined,
    estimated_traffic: (row.estimated_traffic as string) ?? undefined,
  }
}
