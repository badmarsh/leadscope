/**
 * GET /api/usage?campaign_id=1
 * Returns real api_call_log and provider_budgets data for the usage readout.
 */
import { cookies } from "next/headers"
import { NextRequest, NextResponse } from "next/server"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"
import { query, queryOne } from "@/lib/db"

export async function GET(request: NextRequest) {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { searchParams } = new URL(request.url)
  const campaignId = searchParams.get("campaign_id") ?? "1"

  // Month-to-date spend from api_call_log
  const spend = await query<{ provider: string; total_cost: number; total_queries: number }>(
    `SELECT
       provider,
       COALESCE(SUM(cost_estimate_usd), 0) AS total_cost,
       COALESCE(SUM(query_count), 0) AS total_queries
     FROM api_call_log
     WHERE campaign_id = $1
       AND created_at >= date_trunc('month', NOW())
     GROUP BY provider`,
    [campaignId],
  )

  // Provider budgets
  const budgets = await query<{ provider: string; monthly_query_limit: number }>(
    `SELECT provider, monthly_quota AS monthly_query_limit
     FROM provider_budgets`,
    [],
  )

  // Total candidates and evaluations for this campaign
  const stats = await queryOne<{
    total_candidates: number
    pending_review: number
    approved: number
    rejected: number
    enrichment_failed: number
  }>(
    `SELECT
       COUNT(*) AS total_candidates,
       COUNT(*) FILTER (WHERE status = 'pending_review') AS pending_review,
       COUNT(*) FILTER (WHERE status = 'approved') AS approved,
       COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
       COUNT(*) FILTER (WHERE status = 'enrichment_failed') AS enrichment_failed
     FROM candidates
     WHERE campaign_id = $1`,
    [campaignId],
  )

  return NextResponse.json({ spend, budgets, stats })
}
