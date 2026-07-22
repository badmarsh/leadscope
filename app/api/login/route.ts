import { cookies } from "next/headers"
import { NextResponse } from "next/server"
import { compare } from "bcryptjs"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"

export async function POST(request: Request) {
  let body: { password?: string }
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 })
  }

  const { password } = body
  if (!password || typeof password !== "string") {
    return NextResponse.json({ error: "Password is required" }, { status: 400 })
  }

  const hash = process.env.DASHBOARD_PASSWORD_HASH
  if (!hash) {
    return NextResponse.json({ error: "Server misconfigured" }, { status: 500 })
  }

  const valid = await compare(password, hash)
  if (!valid) {
    return NextResponse.json({ error: "Invalid password" }, { status: 401 })
  }

  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  session.loggedIn = true
  await session.save()

  return NextResponse.json({ ok: true })
}
