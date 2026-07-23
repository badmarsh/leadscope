import { NextResponse } from "next/server"
import { query } from "@/lib/db"

export const dynamic = "force-dynamic"

export async function GET() {
  try {
    // 1. Stage statuses from campaigns table
    const campaigns: any[] = await query(`
      SELECT id, slug, stage1_status, stage2_status, stage3_status, stage5_status 
      FROM campaigns 
      WHERE status = 'active'
    `)

    // 2. Candidate counts per status
    const statusCounts: any[] = await query(`
      SELECT status, count(*) as count 
      FROM candidates 
      GROUP BY status
    `)

    // 3. Cost aggregates (today vs this week)
    const costAggregates: any[] = await query(`
      SELECT 
        SUM(CASE WHEN created_at >= NOW() - INTERVAL '1 day' THEN cost_estimate_usd ELSE 0 END) as cost_today,
        SUM(CASE WHEN created_at >= NOW() - INTERVAL '7 days' THEN cost_estimate_usd ELSE 0 END) as cost_week
      FROM api_call_log
    `)

    // 4. Stuck candidates alerts (e.g. enrichment_attempt_count >= max limit or stuck in running too long)
    const stuckCandidates: any[] = await query(`
      SELECT count(*) as count
      FROM candidates
      WHERE status IN ('evaluated', 'pending_review', 'approved') 
        AND enrichment_attempted_at < NOW() - INTERVAL '1 hour'
        AND id NOT IN (SELECT candidate_id FROM leads WHERE enrichment_report IS NOT NULL)
    `)

    return NextResponse.json({
      ok: true,
      data: {
        campaigns,
        statusCounts: statusCounts.reduce((acc, row) => {
          acc[row.status] = parseInt(row.count)
          return acc
        }, {}),
        cost: {
          today: parseFloat(costAggregates[0].cost_today || 0),
          week: parseFloat(costAggregates[0].cost_week || 0)
        },
        stuckEnrichments: parseInt(stuckCandidates[0].count)
      }
    })
  } catch (error) {
    console.error("Health endpoint error:", error)
    return NextResponse.json({ ok: false, error: "Internal server error" }, { status: 500 })
  }
}
