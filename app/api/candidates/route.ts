/**
 * GET /api/candidates?campaign_id=1
 * Returns raw candidates (pre-evaluation pipeline) for the Pipeline tab.
 * Shows candidates with status: new, evaluating, evaluated, discarded, duplicate, enrichment_failed
 */
import { cookies } from "next/headers"
import { NextRequest, NextResponse } from "next/server"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"
import { query } from "@/lib/db"

export async function GET(request: NextRequest) {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { searchParams } = new URL(request.url)
  const campaignId = parseInt(searchParams.get("campaign_id") ?? "1", 10)
  const page = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10))
  const limit = Math.min(200, Math.max(1, parseInt(searchParams.get("limit") ?? "100", 10)))
  const offset = (page - 1) * limit

  const countRow = await query<{ count: string }>(
    `SELECT COUNT(*) FROM candidates
     WHERE campaign_id = $1
       AND status IN ('new', 'evaluating', 'evaluated', 'discarded', 'duplicate', 'enrichment_failed')`,
    [campaignId]
  )
  const total = parseInt(countRow[0]?.count ?? "0", 10)

  const rows = await query<{
    id: number
    domain: string
    company_name: string | null
    source: string
    status: string
    created_at: string
    enrichment_attempt_count: number
    duplicate_of_candidate_id: number | null
  }>(
    `SELECT
       c.id,
       c.domain,
       c.company_name,
       c.source,
       c.status,
       c.created_at,
       c.enrichment_attempt_count,
       c.duplicate_of_candidate_id
     FROM candidates c
     WHERE c.campaign_id = $1
       AND c.status IN ('new', 'evaluating', 'evaluated', 'discarded', 'duplicate', 'enrichment_failed')
     ORDER BY c.created_at DESC
     LIMIT $2 OFFSET $3`,
    [campaignId, limit, offset]
  )

  return NextResponse.json({ candidates: rows, total, page, limit })
}
