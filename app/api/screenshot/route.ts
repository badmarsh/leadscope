import { NextRequest, NextResponse } from "next/server"
import { cookies } from "next/headers"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"

// Block SSRF attempts against private / link-local ranges
const BLOCKED_HOSTNAME_PATTERNS = [
  /^localhost$/i,
  /^127\./,
  /^10\./,
  /^192\.168\./,
  /^172\.(1[6-9]|2[0-9]|3[01])\./,
  /^169\.254\./,
  /^::1$/,
]

function isSafeUrl(raw: string): boolean {
  try {
    const parsed = new URL(raw)
    if (!['http:', 'https:'].includes(parsed.protocol)) return false
    return !BLOCKED_HOSTNAME_PATTERNS.some((re) => re.test(parsed.hostname))
  } catch {
    return false
  }
}

export async function GET(request: NextRequest) {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { searchParams } = new URL(request.url)
  const targetUrl = searchParams.get("url")

  if (!targetUrl) {
    return NextResponse.json({ error: "Missing url parameter" }, { status: 400 })
  }

  if (!isSafeUrl(targetUrl)) {
    return NextResponse.json({ error: "Invalid or disallowed URL" }, { status: 400 })
  }

  try {
    const browserlessUrl = process.env.BROWSERLESS_URL || "http://browserless:3000/screenshot"
    const response = await fetch(browserlessUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: targetUrl,
        options: { type: "jpeg", quality: 70, fullPage: false },
        viewport: { width: 1280, height: 800 }
      })
    })

    if (!response.ok) {
      console.error(`Browserless error: ${response.status} ${response.statusText}`)
      return NextResponse.json({ error: "Failed to generate screenshot" }, { status: response.status })
    }

    const arrayBuffer = await response.arrayBuffer()
    const buffer = Buffer.from(arrayBuffer)

    return new NextResponse(buffer, {
      headers: {
        "Content-Type": "image/jpeg",
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=43200"
      }
    })
  } catch (error) {
    console.error("Screenshot error:", error)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}
