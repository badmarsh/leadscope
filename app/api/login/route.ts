import { cookies } from "next/headers"
import { NextRequest, NextResponse } from "next/server"
import { compare } from "bcryptjs"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"
import { isRateLimited, clearAttempts } from "@/lib/rate-limit"

export async function POST(request: NextRequest) {
  // Rate limiting: extract real IP from proxy headers or fallback
  const ip =
    request.headers.get("x-forwarded-for")?.split(",")[0].trim() ??
    request.headers.get("x-real-ip") ??
    "unknown"

  if (isRateLimited(ip)) {
    return NextResponse.json(
      { error: "Too many login attempts. Try again in 15 minutes." },
      { status: 429 },
    )
  }

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

  // Clear failed attempts on successful login
  clearAttempts(ip)

  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  session.loggedIn = true
  session.username = "admin" // single-operator model; extend when multi-user is added
  await session.save()

  return NextResponse.json({ ok: true })
}
