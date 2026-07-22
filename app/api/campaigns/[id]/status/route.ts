import { cookies } from "next/headers"
import { NextRequest, NextResponse } from "next/server"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"
import { queryOne } from "@/lib/db"

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { id } = await params
  const row = await queryOne<{
    stage1_status: string
    stage1_last_run: string | null
    stage2_status: string
    stage2_last_run: string | null
    stage3_status: string
    stage3_last_run: string | null
    stage5_status: string
    stage5_last_run: string | null
  }>(
    `SELECT 
      stage1_status, stage1_last_run,
      stage2_status, stage2_last_run,
      stage3_status, stage3_last_run,
      stage5_status, stage5_last_run
    FROM campaigns WHERE id = $1`,
    [id],
  )

  if (!row) return NextResponse.json({ error: "Campaign not found" }, { status: 404 })

  return NextResponse.json({ status: row })
}
