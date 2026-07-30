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

  const { candidate_ids, decision } = await request.json()

  if (!Array.isArray(candidate_ids) || candidate_ids.length === 0 || !decision) {
    return NextResponse.json({ error: "Invalid request" }, { status: 400 })
  }

  try {
    const reviewedBy = (session.username ?? "dashboard") + "_bulk"

    if (decision === "approved" || decision === "rejected") {
      // Insert feedback rows for all candidate_ids
      await query(
        `INSERT INTO feedback (candidate_id, decision, reviewed_by)
         SELECT unnest($1::int[]), $2, $3`,
        [candidate_ids, decision, reviewedBy]
      )

      // Flip candidate statuses
      await query(
        `UPDATE candidates SET status = $1 WHERE id = ANY($2::int[])`,
        [decision, candidate_ids]
      )
    } else if (decision === "rerun_evaluation") {
      await query(
        `UPDATE candidates 
         SET status = 'new', 
             enrichment_attempted_at = NULL, 
             enrichment_attempt_count = 0,
             processing_generation = processing_generation + 1,
             lease_id = NULL,
             lease_expires_at = NULL
         WHERE id = ANY($1::int[])`,
        [candidate_ids]
      )
      await query(
        `DELETE FROM evaluations WHERE candidate_id = ANY($1::int[])`,
        [candidate_ids]
      )
      await query(
        `DELETE FROM leads WHERE candidate_id = ANY($1::int[])`,
        [candidate_ids]
      )
      
      // Trigger evaluation in the background
      fetch(`http://evaluator:8000/score/trigger?background=true`, {
        method: "POST",
        headers: {
          "X-Internal-Token": process.env.INTERNAL_API_TOKEN || ""
        }
      }).catch(err => console.error("Failed to trigger evaluator:", err))
    } else if (decision === "rerun_enrichment") {
      await query(
        `UPDATE candidates 
         SET status = CASE WHEN status = 'enrichment_failed' THEN 'evaluated' ELSE status END,
             enrichment_attempted_at = NULL, 
             enrichment_attempt_count = 0,
             processing_generation = processing_generation + 1,
             lease_id = NULL,
             lease_expires_at = NULL
         WHERE id = ANY($1::int[])`,
        [candidate_ids]
      )
      await query(
        `DELETE FROM leads WHERE candidate_id = ANY($1::int[])`,
        [candidate_ids]
      )

      // Trigger enrichment in the background
      fetch(`http://stages:8000/stage5/run?background=true`, {
        method: "POST",
        headers: {
          "X-Internal-Token": process.env.INTERNAL_API_TOKEN || ""
        }
      }).catch(err => console.error("Failed to trigger stages:", err))
    } else if (decision === "junk") {
      // 1. Fetch domains for these candidates to blocklist them globally
      const res = await query(
        `SELECT domain FROM candidates WHERE id = ANY($1::int[])`,
        [candidate_ids]
      )
      const domains = (res as any[]).map(row => row.domain)
      
      if (domains.length > 0) {
        // Insert into do_not_contact globally (campaign_id = null)
        // using ON CONFLICT DO NOTHING in case it's already there
        await query(
          `INSERT INTO do_not_contact (domain, reason)
           SELECT unnest($1::text[]), 'Marked as junk in dashboard'
           ON CONFLICT (domain, campaign_id) DO NOTHING`,
          [domains]
        )
      }

      // 2. Set status to 'junk'
      await query(
        `UPDATE candidates 
         SET status = 'junk'
         WHERE id = ANY($1::int[])`,
        [candidate_ids]
      )
    } else {
      return NextResponse.json({ error: "Unknown action" }, { status: 400 })
    }

    return NextResponse.json({ ok: true })
  } catch (error) {
    console.error("Bulk action failed:", error)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}
