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

  const statusCondition = statusFilter
    ? `AND c.status = $2`
    : `AND c.status IN ('pending_review', 'approved', 'rejected', 'enrichment_failed')`

  const values: unknown[] = [campaignId]
  if (statusFilter) values.push(statusFilter)

  const page = parseInt(searchParams.get("page") ?? "1", 10)
  const rawLimit = parseInt(searchParams.get("limit") ?? "200", 10)
  const limit = Math.min(Math.max(1, isNaN(rawLimit) ? 200 : rawLimit), 500)
  const offset = (page - 1) * limit

  // Count total matching leads
  const countRow = await query<{ count: string }>(
    `SELECT COUNT(*) FROM candidates c WHERE c.campaign_id = $1 ${statusCondition}`,
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
      l.estimated_traffic
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
    ORDER BY e.score DESC NULLS LAST, c.created_at DESC
    LIMIT $${values.length + 1} OFFSET $${values.length + 2}
    `,
    [...values, limit, offset],
  )

  return NextResponse.json({ leads: rows, total, page, limit })
}
