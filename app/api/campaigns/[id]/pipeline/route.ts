import { cookies } from "next/headers"
import { NextRequest, NextResponse } from "next/server"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"
import { query, queryOne } from "@/lib/db"

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { id } = await params
  const campaignId = parseInt(id, 10)
  if (isNaN(campaignId)) {
    return NextResponse.json({ error: "Invalid campaign ID" }, { status: 400 })
  }

  const { action, stage } = await request.json()

  if (!["start", "stop"].includes(action)) {
    return NextResponse.json({ error: "Invalid action" }, { status: 400 })
  }
  // Allowlist stage names — mirrors db.py _VALID_STAGES
  if (!["stage1", "stage2", "stage3", "stage5"].includes(stage)) {
    return NextResponse.json({ error: "Invalid stage" }, { status: 400 })
  }

  if (action === "stop") {
    // Just update the database flag to 'stopping'
    // The Python scripts will pick this up on their next loop iteration
    await query(`UPDATE campaigns SET ${stage}_status = 'stopping' WHERE id = $1`, [campaignId])
    return NextResponse.json({ ok: true, message: "Stop signal sent" })
  }

  if (action === "start") {
    // C4: Guard against double-start — return 409 if stage is already running or stopping
    const campaign = await queryOne<Record<string, string>>(
      `SELECT ${stage}_status AS current_status FROM campaigns WHERE id = $1`,
      [campaignId],
    )
    if (!campaign) {
      return NextResponse.json({ error: "Campaign not found" }, { status: 404 })
    }
    const currentStatus = campaign["current_status"]
    if (currentStatus === "running" || currentStatus === "stopping") {
      return NextResponse.json(
        { error: `Stage is already ${currentStatus}. Stop it first before starting a new run.` },
        { status: 409 },
      )
    }

    // Make request to the appropriate Python container endpoint
    let url = ""
    let body: any = undefined

    const STAGES_URL = process.env.STAGES_URL || "http://127.0.0.1:8002"
    const EVALUATOR_URL = process.env.EVALUATOR_URL || "http://127.0.0.1:8001"

    if (stage === "stage1" || stage === "stage2") {
      url = `${STAGES_URL}/${stage}/run?background=true`
      body = { campaign_id: campaignId }
    } else if (stage === "stage5") {
      url = `${STAGES_URL}/stage5/run?background=true`
      body = { campaign_id: campaignId }
    } else if (stage === "stage3") {
      url = `${EVALUATOR_URL}/score/trigger?background=true`
      body = { campaign_id: campaignId }
    }

    try {
      // The backend acquires the lock atomatically; we do not pre-emptively set status to running

      const res = await fetch(url, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "X-Internal-Token": process.env.INTERNAL_API_TOKEN || "" 
        },
        body: body ? JSON.stringify(body) : undefined,
      })

      if (!res.ok) {
        // We do not revert status here, backend controls it.
        const errText = await res.text()
        return NextResponse.json({ error: `Pipeline trigger failed: ${errText}` }, { status: res.status })
      }

      return NextResponse.json({ ok: true, message: "Pipeline started" })
    } catch (err: unknown) {
      // We do not revert status here, backend controls it.
      const message = err instanceof Error ? err.message : String(err)
      return NextResponse.json({ error: `Failed to connect to pipeline service: ${message}` }, { status: 500 })
    }
  }

  return NextResponse.json({ error: "Unknown error" }, { status: 500 })
}
