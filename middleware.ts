/**
 * middleware.ts — Gates every dashboard route and API (except /api/login)
 * behind a valid iron-session cookie.
 */
import { NextRequest, NextResponse } from "next/server"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"

// Routes that don't require a session
const PUBLIC_PATHS = ["/api/login", "/api/session", "/login", "/_next", "/favicon.ico"]

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Allow public paths
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next()
  }

  // Check session
  const cookieHeader = request.cookies.get(sessionOptions.cookieName)

  if (!cookieHeader?.value) {
    // API calls get 401; page navigation gets redirect to login page
    if (pathname.startsWith("/api/")) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
    }
    return NextResponse.redirect(new URL("/login", request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    // Match all paths except Next.js internals and static files
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
}
