/**
 * GET /api/leads?campaign_id=1&status=pending_review
 * Returns leads (candidates + evaluations) for a campaign.
 * Gated by session cookie.
 */
import { cookies } from "next/headers"
import { NextRequest, NextResponse } from "next/server"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"
import { query } from "@/lib/db"
import { CAMPAIGN_SLUG_TO_ID } from "@/lib/campaigns"  // M3: single source of truth

export async function GET(request: NextRequest) {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { searchParams } = new URL(request.url)
  const campaignParam = searchParams.get("campaign_id") ?? "jenex"
  const statusFilter = searchParams.get("status") // optional filter

  // Resolve campaign slug or numeric ID
  let campaignId: number
  if (/^\d+$/.test(campaignParam)) {
    campaignId = parseInt(campaignParam, 10)
  } else {
    campaignId = CAMPAIGN_SLUG_TO_ID[campaignParam] ?? 1
  }

  const hideBroken = searchParams.get("hide_broken") !== "false" // default true
  const requireEnrichment = searchParams.get("require_enrichment") === "true"

  // Hide approved leads that don't have proper enrichment data
  const enrichmentFilter = hideBroken 
    ? `AND (c.status != 'approved' OR (l.estimated_size IS NOT NULL AND l.estimated_revenue IS NOT NULL))`
    : ``

  // When require_enrichment=true, only show leads with full enrichment in the main queue
  const enrichedFilter = requireEnrichment
    ? `AND (c.status NOT IN ('pending_review', 'approved') OR l.enrichment_report IS NOT NULL)`
    : ``

  const statusCondition = statusFilter
    ? `AND c.status = $2 ${enrichmentFilter} ${enrichedFilter}`
    : `AND c.status IN ('pending_review', 'approved', 'rejected', 'enrichment_failed') ${enrichmentFilter} ${enrichedFilter}`

  const values: unknown[] = [campaignId]
  if (statusFilter) values.push(statusFilter)

  const page = parseInt(searchParams.get("page") ?? "1", 10)
  const rawLimit = parseInt(searchParams.get("limit") ?? "50", 10)
  const limit = Math.min(Math.max(1, isNaN(rawLimit) ? 50 : rawLimit), 200)
  const offset = (page - 1) * limit

  const queryValues = [...values]
  const cursor = searchParams.get("cursor")
  let cursorCondition = ""
  if (cursor) {
    cursorCondition = `AND c.id < $${queryValues.length + 1}`
    queryValues.push(parseInt(cursor, 10))
  }

  const limitParamIdx = queryValues.length + 1
  const offsetParamIdx = queryValues.length + 2
  queryValues.push(limit, offset)

  // Count total matching leads (must include the joins to filter by l.estimated_size)
  const countRow = await query<{ count: string }>(
    `
    SELECT COUNT(*) 
    FROM candidates c
    LEFT JOIN evaluations e ON c.id = e.candidate_id
    LEFT JOIN leads l ON c.id = l.candidate_id
    WHERE c.campaign_id = $1 ${statusCondition}
    `,
    values
  )
  const total = parseInt(countRow[0]?.count ?? "0", 10)

  const rows = await query<{
    id: number
    campaign_id: number
    domain: string
    company_name: string | null
    source: string
    status: string
    created_at: string
    score: number | null
    rationale: string | null
    evidence_urls: string[] | null
    evidence_data: Record<string, unknown> | null
    model_used: string | null
    icp_version_used: number | null
    eval_id: number | null
    note: string | null
    contact_email: string | null
    contact_phone: string | null
    contact_name: string | null
    screenshot_url: string | null
    products_sold: string[] | null
    enrichment_report: string | null
    estimated_size: string | null
    estimated_revenue: string | null
    estimated_traffic: string | null
    audit_token: string | null
    mainwp_webhook_token: string | null
  }>(
    `
    SELECT
      c.id,
      c.campaign_id,
      c.domain,
      c.company_name,
      c.source,
      c.status,
      c.created_at,
      e.score,
      e.rationale,
      e.evidence_urls,
      e.evidence_data,
      e.model_used,
      e.icp_version_used,
      e.id AS eval_id,
      f.note,
      l.contact_email,
      l.contact_phone,
      l.contact_name,
      l.screenshot_url,
      l.products_sold,
      l.enrichment_report,
      l.draft_email,
      l.estimated_size,
      l.estimated_revenue,
      l.estimated_traffic,
      c.audit_token,
      l.mainwp_webhook_token
    FROM candidates c
    LEFT JOIN LATERAL (
      SELECT * FROM evaluations WHERE candidate_id = c.id
      ORDER BY created_at DESC LIMIT 1
    ) e ON true
    LEFT JOIN LATERAL (
      SELECT note FROM feedback WHERE candidate_id = c.id
      ORDER BY created_at DESC LIMIT 1
    ) f ON true
    LEFT JOIN leads l ON l.candidate_id = c.id
    WHERE c.campaign_id = $1
    ${statusCondition}
    ${cursorCondition}
    ORDER BY e.score DESC NULLS LAST, c.id DESC
    LIMIT $${limitParamIdx} OFFSET $${offsetParamIdx}
    `,
    queryValues,
  )

  const nextCursor = rows.length === limit ? rows[rows.length - 1].id : null

  return NextResponse.json({ leads: rows, total, page, limit, nextCursor })
}
