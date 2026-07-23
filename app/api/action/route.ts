/**
 * POST /api/action
 * Body: { candidate_id: number, decision: "approved" | "rejected", note?: string }
 * Writes a feedback row and flips candidates.status.
 *
 * PATCH /api/action
 * Body: { candidate_id: number }
 * Reopens a decided/enriched lead → resets status to pending_review
 * and clears enrichment retry state so Stage 5 will re-attempt (C3).
 */
import { cookies } from "next/headers"
import { NextRequest, NextResponse } from "next/server"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"
import { query } from "@/lib/db"
import { z } from "zod"
import crypto from "crypto"

const actionSchema = z.object({
  candidate_id: z.number(),
  decision: z.enum(["approved", "rejected"]),
  note: z.string().optional(),
})

const patchSchema = z.object({
  candidate_id: z.number(),
})

export async function POST(request: NextRequest) {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const body = await request.json().catch(() => ({}))
  const parsed = actionSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid request", details: parsed.error }, { status: 400 })
  }
  let { candidate_id, decision, note } = parsed.data

  const reviewedBy = session.username ?? "dashboard"

  if (decision === "approved") {
    // Check DNC list
    const dncCheck: any[] = await query(
      `SELECT 1 FROM do_not_contact d 
       JOIN candidates c ON LOWER(c.domain) = LOWER(d.domain) OR c.domain LIKE '%.' || d.domain
       WHERE c.id = $1 AND (d.campaign_id = c.campaign_id OR d.campaign_id IS NULL)
       LIMIT 1`,
      [candidate_id]
    )
    if (dncCheck.length > 0) {
      decision = "rejected"
      note = (note ? note + " | " : "") + "Auto-rejected: Domain found on DNC list."
    }
  }

  // Write feedback row
  await query(
    `INSERT INTO feedback (candidate_id, decision, note, reviewed_by)
     VALUES ($1, $2, $3, $4)`,
    [candidate_id, decision, note ?? null, reviewedBy],
  )

  // Flip candidate status
  await query(
    `UPDATE candidates SET status = $1 WHERE id = $2`,
    [decision, candidate_id],
  )

  if (decision === "approved") {
    // Deliver webhook if configured in campaign settings
    const campInfo: any[] = await query(
      `SELECT camp.settings, c.domain FROM candidates c
       JOIN campaigns camp ON camp.id = c.campaign_id
       WHERE c.id = $1`,
      [candidate_id]
    )
    if (campInfo.length > 0) {
      let settings = campInfo[0].settings
      if (typeof settings === "string") {
        try { settings = JSON.parse(settings) } catch(e) { settings = {} }
      }
      const webhookUrl = settings?.webhook_url
      if (webhookUrl) {
        const tsMinute = Math.floor(Date.now() / 60000)
        const idempotencyKey = crypto.createHash('sha256').update(`${candidate_id}:${tsMinute}`).digest('hex')
        try {
          fetch(webhookUrl, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-LeadScope-Idempotency-Key": idempotencyKey
            },
            body: JSON.stringify({ event: "lead_approved", candidate_id, domain: campInfo[0].domain })
          }).catch(e => console.error("Webhook fetch error:", e))
        } catch (e) {
          console.error("Webhook error:", e)
        }
      }
    }
  }

  return NextResponse.json({ ok: true })
}

export async function PATCH(request: NextRequest) {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const body = await request.json().catch(() => ({}))
  const parsed = patchSchema.safeParse(body)

  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid request", details: parsed.error }, { status: 400 })
  }
  const { candidate_id } = parsed.data

  // C3: Reset status AND enrichment retry state so Stage 5 will re-attempt.
  // Without resetting enrichment_attempted_at and enrichment_attempt_count,
  // a lead that hit max_enrichment_attempts would be immediately re-failed on the next Stage 5 run.
  await query(
    `UPDATE candidates
     SET status = 'pending_review',
         enrichment_attempted_at = NULL,
         enrichment_attempt_count = 0
     WHERE id = $1`,
    [candidate_id],
  )

  // M-06: Also clear the enrichment_report in leads so Stage 5 doesn't see
  // existing_enrichment_report and skip the re-enrich attempt.
  await query(
    `UPDATE leads SET enrichment_report = NULL WHERE candidate_id = $1`,
    [candidate_id],
  )

  return NextResponse.json({ ok: true })
}
