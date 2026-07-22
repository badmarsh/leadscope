import { NextResponse } from "next/server"
import { pool } from "@/lib/db"

export async function GET() {
  try {
    const { rows } = await pool.query(`
      SELECT id, name, nodes, connections, "createdAt", "updatedAt"
      FROM workflow_entity
      ORDER BY name ASC
    `)

    return NextResponse.json({ workflows: rows })
  } catch (error: unknown) {
    console.error("Failed to fetch n8n workflows:", error)
    return NextResponse.json({ error: "Failed to fetch workflows" }, { status: 500 })
  }
}
