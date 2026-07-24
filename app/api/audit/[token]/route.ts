import { NextRequest, NextResponse } from "next/server"
import { query } from "@/lib/db"

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ token: string }> }
) {
  const { token } = await params

  if (!token || token.length < 32) {
    return NextResponse.json({ error: "Invalid token" }, { status: 400 })
  }

  // Find candidate by audit_token
  const rows: any[] = await query(
    `SELECT c.domain, c.company_name, e.score, e.rationale, e.evidence_data, c.audit_view_count
     FROM candidates c
     JOIN evaluations e ON e.candidate_id = c.id
     WHERE c.audit_token = $1
     ORDER BY e.created_at DESC LIMIT 1`,
    [token]
  )

  if (rows.length === 0) {
    return NextResponse.json({ error: "Audit not found or expired" }, { status: 404 })
  }

  const row = rows[0]
  const evidence = typeof row.evidence_data === "string" 
    ? JSON.parse(row.evidence_data) 
    : (row.evidence_data ?? {})

  // Update view count and timestamp
  await query(
    `UPDATE candidates SET 
      audit_viewed_at = now(),
      audit_view_count = audit_view_count + 1
     WHERE audit_token = $1`,
    [token]
  )

  return NextResponse.json({
    domain: row.domain,
    company_name: row.company_name,
    score: row.score,
    rationale: row.rationale,
    evidence: {
      malware_family: evidence.malware_family,
      confidence: evidence.confidence,
      exposure_scan: evidence.exposure_scan ?? null,
      proof_data: evidence.proof_data ?? null,
      sucuri_scan_url: `https://sitecheck.sucuri.net/results/${row.domain}`,
      virustotal_url: `https://www.virustotal.com/gui/domain/${row.domain}`,
    },
    view_count: (row.audit_view_count ?? 0) + 1
  })
}
