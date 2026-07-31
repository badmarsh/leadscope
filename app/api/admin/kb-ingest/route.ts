import { cookies } from "next/headers"
import { NextResponse } from "next/server"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"

export async function POST() {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const internalToken = process.env.INTERNAL_API_TOKEN
  if (!internalToken) {
    return NextResponse.json({ error: "Server misconfiguration: missing internal API token" }, { status: 500 })
  }

  try {
    const STAGES_URL = process.env.STAGES_URL || "http://127.0.0.1:8002"
    const res = await fetch(`${STAGES_URL}/kb/ingest?background=true`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Token": internalToken
      }
    })

    if (!res.ok) {
      const text = await res.text()
      return NextResponse.json({ error: `Stages service failed: ${res.status} ${text}` }, { status: res.status })
    }

    const data = await res.json()
    return NextResponse.json(data)
  } catch (e: any) {
    console.error("Failed to trigger KB Ingestion:", e)
    return NextResponse.json({ error: `Failed to trigger KB Ingestion: ${e.message}` }, { status: 500 })
  }
}
