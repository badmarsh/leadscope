import { cookies } from "next/headers"
import { NextResponse } from "next/server"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"
import { pool } from "@/lib/db"

export async function GET() {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  try {
    const { rows } = await pool.query(`
      SELECT DISTINCT ON (name) id, name, nodes, connections, "createdAt", "updatedAt"
      FROM workflow_entity
      ORDER BY name ASC, active DESC, "updatedAt" DESC
    `)

    return NextResponse.json({ workflows: rows })
  } catch (error: unknown) {
    console.error("Failed to fetch n8n workflows:", error)
    return NextResponse.json({ error: "Failed to fetch workflows" }, { status: 500 })
  }
}
