/**
 * POST /api/leads/export/crm
 * Body: { campaign_id: number, webhook_url: string }
 * Pushes approved+enriched leads to a CRM webhook (HubSpot, Pipedrive, n8n, Zapier, etc.)
 */
import { cookies } from "next/headers"
import { NextRequest, NextResponse } from "next/server"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"
import { query } from "@/lib/db"

export async function POST(request: NextRequest) {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const body = await request.json()
  const { campaign_id, webhook_url } = body

  if (!campaign_id || !webhook_url) {
    return NextResponse.json({ error: "campaign_id and webhook_url are required" }, { status: 400 })
  }

  // Basic URL validation — must be https
  try {
    const url = new URL(webhook_url)
    if (url.protocol !== "https:") throw new Error("Must be HTTPS")
  } catch {
    return NextResponse.json({ error: "webhook_url must be a valid HTTPS URL" }, { status: 400 })
  }

  const rows = await query<{
    domain: string
    company_name: string | null
    contact_email: string | null
    contact_name: string | null
    contact_phone: string | null
    score: number | null
    enrichment_report: string | null
    products_sold: string[] | null
  }>(
    `SELECT c.domain, c.company_name, l.contact_email, l.contact_name,
            l.contact_phone, e.score, l.enrichment_report, l.products_sold
     FROM candidates c
     LEFT JOIN leads l ON l.candidate_id = c.id
     LEFT JOIN LATERAL (
       SELECT score FROM evaluations WHERE candidate_id = c.id
       ORDER BY created_at DESC LIMIT 1
     ) e ON true
     WHERE c.campaign_id = $1 AND c.status = 'approved'
     ORDER BY e.score DESC NULLS LAST`,
    [campaign_id],
  )

  // HubSpot-compatible payload structure
  const payload = {
    source: "leadscope",
    campaign_id,
    exported_at: new Date().toISOString(),
    leads: rows.map((r) => ({
      properties: {
        domain: r.domain,
        company: r.company_name,
        email: r.contact_email,
        firstname: r.contact_name?.split(" ")[0] ?? null,
        lastname: r.contact_name?.split(" ").slice(1).join(" ") ?? null,
        phone: r.contact_phone,
        leadscope_score: r.score,
        description: r.enrichment_report,
      },
    })),
  }

  try {
    const resp = await fetch(webhook_url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })

    if (!resp.ok) {
      return NextResponse.json(
        { error: `Webhook returned ${resp.status}` },
        { status: 502 },
      )
    }

    return NextResponse.json({ ok: true, exported: rows.length })
  } catch (err) {
    return NextResponse.json(
      { error: `Webhook delivery failed: ${err instanceof Error ? err.message : String(err)}` },
      { status: 502 },
    )
  }
}
