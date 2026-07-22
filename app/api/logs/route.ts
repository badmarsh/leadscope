import { NextResponse } from 'next/server'
import fs from 'fs/promises'
import { cookies } from "next/headers"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"

const LOG_FILE = '/var/log/app/system.log'
const MAX_BYTES = 50_000 // Read at most last 50 KB

export async function GET() {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  try {
    const stat = await fs.stat(LOG_FILE).catch(() => null)
    if (!stat) {
      return NextResponse.json({ logs: 'Logs not initialized yet...' })
    }

    // Read only the tail (last MAX_BYTES) without shelling out
    const fd = await fs.open(LOG_FILE, 'r')
    const start = Math.max(0, stat.size - MAX_BYTES)
    const buffer = Buffer.alloc(stat.size - start)
    await fd.read(buffer, 0, buffer.length, start)
    await fd.close()

    const logs = buffer.toString('utf-8')
    // If we started mid-line, trim to first newline for cleanliness
    const firstNl = logs.indexOf('\n')
    return NextResponse.json({ logs: start > 0 && firstNl > -1 ? logs.slice(firstNl + 1) : logs })
  } catch (error) {
    console.error('Failed to read logs:', error)
    return NextResponse.json({ logs: 'Error reading system logs.' }, { status: 500 })
  }
}
