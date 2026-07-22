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

export async function POST(request: NextRequest) {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { candidate_id, decision, note } = await request.json()

  if (!candidate_id || !["approved", "rejected"].includes(decision)) {
    return NextResponse.json({ error: "Invalid request" }, { status: 400 })
  }

  // Write feedback row
  await query(
    `INSERT INTO feedback (candidate_id, decision, note, reviewed_by)
     VALUES ($1, $2, $3, 'dashboard')`,
    [candidate_id, decision, note ?? null],
  )

  // Flip candidate status
  await query(
    `UPDATE candidates SET status = $1 WHERE id = $2`,
    [decision, candidate_id],
  )

  return NextResponse.json({ ok: true })
}

export async function PATCH(request: NextRequest) {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { candidate_id } = await request.json()

  if (!candidate_id) {
    return NextResponse.json({ error: "Invalid request" }, { status: 400 })
  }

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
