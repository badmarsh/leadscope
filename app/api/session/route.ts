/**
 * GET /api/session — returns {loggedIn: bool}
 * Used by the dashboard to check auth state on load.
 */
import { cookies } from "next/headers"
import { NextResponse } from "next/server"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"

export async function GET() {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  return NextResponse.json({ loggedIn: session.loggedIn === true })
}
