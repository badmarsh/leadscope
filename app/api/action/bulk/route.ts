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
         SET status = 'new'
         WHERE id = ANY($1::int[])`,
        [candidate_ids]
      )
      await query(
        `DELETE FROM evaluations WHERE candidate_id = ANY($1::int[])`,
        [candidate_ids]
      )
    } else if (decision === "rerun_enrichment") {
      await query(
        `UPDATE candidates 
         SET status = 'evaluated', enrichment_attempted_at = NULL, enrichment_attempt_count = 0 
         WHERE id = ANY($1::int[])`,
        [candidate_ids]
      )
      await query(
        `DELETE FROM leads WHERE candidate_id = ANY($1::int[])`,
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
