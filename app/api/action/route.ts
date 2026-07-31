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
import { pool } from "@/lib/db"
import { z } from "zod"
import crypto from "crypto"

const BLOCKED_HOSTNAME_PATTERNS = [
  /^localhost$/i,
  /^127\./,
  /^10\./,
  /^192\.168\./,
  /^172\.(1[6-9]|2[0-9]|3[01])\./,
  /^169\.254\./,
  /^::1$/,
]

function isSafeUrl(raw: string): boolean {
  try {
    const parsed = new URL(raw)
    if (!['http:', 'https:'].includes(parsed.protocol)) return false
    return !BLOCKED_HOSTNAME_PATTERNS.some((re) => re.test(parsed.hostname))
  } catch {
    return false
  }
}

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

  const client = await pool.connect()
  let settings: any = null
  let domain: string | null = null
  let mainwpToken: string | null = null

  try {
    await client.query("BEGIN")

    if (decision === "approved") {
      // Check DNC list
      const dncCheck = await client.query(
        `SELECT 1 FROM do_not_contact d 
         JOIN candidates c ON LOWER(c.domain) = LOWER(d.domain) OR c.domain LIKE '%.' || d.domain
         WHERE c.id = $1 AND (d.campaign_id = c.campaign_id OR d.campaign_id IS NULL)
         LIMIT 1`,
        [candidate_id]
      )
      if (dncCheck.rows.length > 0) {
        decision = "rejected"
        note = (note ? note + " | " : "") + "Auto-rejected: Domain found on DNC list."
      }
    }

    // Check for existing feedback row to prevent duplicates (Idempotency)
    const feedbackCheck = await client.query(
      `SELECT 1 FROM feedback WHERE candidate_id = $1 AND decision = $2 LIMIT 1`,
      [candidate_id, decision]
    )
    if (feedbackCheck.rows.length === 0) {
      // Write feedback row
      await client.query(
        `INSERT INTO feedback (candidate_id, decision, note, reviewed_by)
         VALUES ($1, $2, $3, $4)`,
        [candidate_id, decision, note ?? null, reviewedBy]
      )
    }

    // Flip candidate status
    await client.query(
      `UPDATE candidates SET status = $1 WHERE id = $2`,
      [decision, candidate_id]
    )

    if (decision === "approved") {
      // Phase X: Generate audit_token for the Shadow Audit dashboard
      const auditToken = crypto.randomBytes(32).toString('hex')
      await client.query(
        `UPDATE candidates SET audit_token = $1, audit_token_created = now() WHERE id = $2 AND audit_token IS NULL`,
        [auditToken, candidate_id]
      )

      // Phase X: Generate MainWP webhook token and upsert lead row
      mainwpToken = crypto.randomBytes(32).toString('hex')
      await client.query(
        `INSERT INTO leads (candidate_id, campaign_id, cold_email_hook)
         VALUES ($1, (SELECT campaign_id FROM candidates WHERE id = $1), $2)
         ON CONFLICT (candidate_id) DO UPDATE SET cold_email_hook = $2`,
        [candidate_id, mainwpToken]
      )

      // Get campaign settings & domain for webhook delivery
      const campInfo = await client.query(
        `SELECT camp.settings, c.domain FROM candidates c
         JOIN campaigns camp ON camp.id = c.campaign_id
         WHERE c.id = $1`,
        [candidate_id]
      )
      if (campInfo.rows.length > 0) {
        settings = campInfo.rows[0].settings
        domain = campInfo.rows[0].domain
      }
    }

    await client.query("COMMIT")
  } catch (err) {
    await client.query("ROLLBACK")
    console.error("Action POST transaction error:", err)
    return NextResponse.json({ error: "Transaction failed" }, { status: 500 })
  } finally {
    client.release()
  }

  // Deliver webhook outside of DB transaction if configured & safe
  if (decision === "approved" && settings) {
    if (typeof settings === "string") {
      try { settings = JSON.parse(settings) } catch { settings = {} }
    }
    const webhookUrl = settings?.webhook_url
    if (webhookUrl && isSafeUrl(webhookUrl)) {
      const tsMinute = Math.floor(Date.now() / 60000)
      const idempotencyKey = crypto.createHash('sha256').update(`${candidate_id}:${tsMinute}`).digest('hex')
      try {
        const controller = new AbortController()
        const timeoutId = setTimeout(() => controller.abort(), 5000)
        fetch(webhookUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-LeadScope-Idempotency-Key": idempotencyKey
          },
          body: JSON.stringify({ 
            event: "lead_approved", 
            candidate_id, 
            domain,
            mainwp_token: mainwpToken
          }),
          signal: controller.signal
        }).catch((e) => console.error("Webhook fetch error:", e))
          .finally(() => clearTimeout(timeoutId))
      } catch (e) {
        console.error("Webhook error:", e)
      }
    } else if (webhookUrl) {
      console.warn("Blocked unsafe webhook URL:", webhookUrl)
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

  const client = await pool.connect()
  try {
    await client.query("BEGIN")
    // C3: Reset status AND enrichment retry state so Stage 5 will re-attempt.
    await client.query(
      `UPDATE candidates
       SET status = 'evaluated',
           enrichment_attempted_at = NULL,
           enrichment_attempt_count = 0
       WHERE id = $1`,
      [candidate_id]
    )

    // M-06: Also clear the enrichment_report in leads so Stage 5 doesn't see
    // existing_enrichment_report and skip the re-enrich attempt.
    await client.query(
      `UPDATE leads SET enrichment_report = NULL WHERE candidate_id = $1`,
      [candidate_id]
    )
    await client.query("COMMIT")
  } catch (err) {
    await client.query("ROLLBACK")
    console.error("Action PATCH transaction error:", err)
    return NextResponse.json({ error: "Transaction failed" }, { status: 500 })
  } finally {
    client.release()
  }

  return NextResponse.json({ ok: true })
}
