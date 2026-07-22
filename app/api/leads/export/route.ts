/**
 * GET /api/leads/export?campaign_id=X&status=approved
 * Streams a CSV of enriched/approved leads for a given campaign.
 * Gated by session cookie (same auth as leads/route.ts).
 */
import { cookies } from "next/headers"
import { NextRequest, NextResponse } from "next/server"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"
import { query } from "@/lib/db"

/** Wrap a field value in double-quotes and escape any internal double-quotes. */
function csvField(value: string | null | undefined): string {
  if (value === null || value === undefined) return ""
  const str = String(value)
  // Escape internal double-quotes by doubling them
  return `"${str.replace(/"/g, '""')}"`
}

export async function GET(request: NextRequest) {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { searchParams } = new URL(request.url)
  const campaignId = parseInt(searchParams.get("campaign_id") ?? "1", 10)
  // Default to approved leads; caller can override via ?status=
  const statusFilter = searchParams.get("status") ?? "approved"

  const rows = await query<{
    domain: string
    company_name: string | null
    contact_email: string | null
    contact_name: string | null
    contact_phone: string | null
    score: number | null
    enrichment_report: string | null
    products_sold: string[] | null
    note: string | null
  }>(
    `SELECT
       c.domain,
       c.company_name,
       l.contact_email,
       l.contact_name,
       l.contact_phone,
       e.score,
       l.enrichment_report,
       l.products_sold,
       f.note
     FROM candidates c
     LEFT JOIN leads l ON l.candidate_id = c.id
     LEFT JOIN LATERAL (
       SELECT score FROM evaluations WHERE candidate_id = c.id
       ORDER BY created_at DESC LIMIT 1
     ) e ON true
     LEFT JOIN LATERAL (
       SELECT note FROM feedback WHERE candidate_id = c.id
       ORDER BY created_at DESC LIMIT 1
     ) f ON true
     WHERE c.campaign_id = $1
       AND c.status = $2
     ORDER BY e.score DESC NULLS LAST`,
    [campaignId, statusFilter],
  )

  // Build CSV
  const header = ["Company", "Domain", "Email", "Phone", "Contact Name", "Score", "Overview", "Products", "Note"]
  const lines: string[] = [header.join(",")]

  for (const row of rows) {
    const products = Array.isArray(row.products_sold)
      ? row.products_sold.join("; ")
      : (row.products_sold ?? "")

    const cols = [
      csvField(row.company_name),
      csvField(row.domain),
      csvField(row.contact_email),
      csvField(row.contact_phone),
      csvField(row.contact_name),
      csvField(row.score !== null ? String(row.score) : null),
      csvField(row.enrichment_report),
      csvField(products),
      csvField(row.note),
    ]
    lines.push(cols.join(","))
  }

  const csv = lines.join("\r\n")

  return new NextResponse(csv, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": "attachment; filename=leads-export.csv",
    },
  })
}
