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

  if (!Array.isArray(candidate_ids) || candidate_ids.length === 0 || !["approved", "rejected"].includes(decision)) {
    return NextResponse.json({ error: "Invalid request" }, { status: 400 })
  }

  // Insert feedback rows for all candidate_ids
  // We use UNNEST($1::int[]) to insert multiple rows in one query.
  await query(
    `INSERT INTO feedback (candidate_id, decision, reviewed_by)
     SELECT unnest($1::int[]), $2, 'dashboard_bulk'`,
    [candidate_ids, decision]
  )

  // Flip candidate statuses
  await query(
    `UPDATE candidates SET status = $1 WHERE id = ANY($2::int[])`,
    [decision, candidate_ids]
  )

  return NextResponse.json({ ok: true })
}
