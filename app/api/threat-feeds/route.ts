import { NextRequest, NextResponse } from "next/server"
import { query } from "@/lib/db"

export async function GET(request: NextRequest) {
  try {
    const rows = await query(`
      SELECT
        c.id,
        c.campaign_id,
        c.domain,
        c.source,
        c.status,
        c.created_at,
        c.evidence_data,
        e.score,
        e.evidence_data as eval_evidence
      FROM candidates c
      LEFT JOIN LATERAL (
        SELECT score, evidence_data FROM evaluations WHERE candidate_id = c.id
        ORDER BY created_at DESC LIMIT 1
      ) e ON true
      WHERE c.source IN ('urlscan', 'publicwww')
      ORDER BY c.created_at DESC
      LIMIT 100
    `)

    return NextResponse.json({ candidates: rows })
  } catch (err) {
    console.error("Failed to fetch threat feeds:", err)
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 })
  }
}
