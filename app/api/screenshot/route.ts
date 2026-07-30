import dns from "dns"
import { NextRequest, NextResponse } from "next/server"
import { cookies } from "next/headers"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"

// Block SSRF attempts against private / link-local / internal ranges
const BLOCKED_HOSTNAME_PATTERNS = [
  /^localhost$/i,
  /^127\./,
  /^10\./,
  /^192\.168\./,
  /^172\.(1[6-9]|2[0-9]|3[01])\./,
  /^169\.254\./,
  /^0\./,
  /^::1$/,
  /^fe80:/i,
  /^fc00:/i,
  /^fd[0-9a-f]{2}:/i,
  /^::ffff:(127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|169\.254\.)/i,
]

function isPrivateIp(ip: string): boolean {
  return BLOCKED_HOSTNAME_PATTERNS.some((re) => re.test(ip))
}

async function resolveSafeUrl(raw: string): Promise<{ safe: boolean, resolvedUrl?: string, originalHostname?: string }> {
  try {
    const parsed = new URL(raw)
    if (!['http:', 'https:'].includes(parsed.protocol)) return { safe: false }

    const hostname = parsed.hostname.toLowerCase()
    if (BLOCKED_HOSTNAME_PATTERNS.some((re) => re.test(hostname))) return { safe: false }

    // Perform DNS resolution to prevent DNS rebinding & mapped IPv6 bypasses
    try {
      const addresses = await dns.promises.lookup(hostname, { all: true })
      if (!addresses || addresses.length === 0) return { safe: false }
      
      let selectedIp = ""
      for (const addr of addresses) {
        if (isPrivateIp(addr.address)) {
          return { safe: false }
        }
        if (!selectedIp) selectedIp = addr.address
      }
      
      const isIPv6 = selectedIp.includes(':')
      const hostValue = isIPv6 ? `[${selectedIp}]` : selectedIp
      
      const newUrl = new URL(raw)
      newUrl.hostname = hostValue
      
      return { 
        safe: true, 
        resolvedUrl: newUrl.toString(), 
        originalHostname: parsed.hostname 
      }
    } catch {
      // If DNS resolution fails, FAIL SECURELY
      return { safe: false }
    }
  } catch {
    return { safe: false }
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

  const validation = await resolveSafeUrl(targetUrl)
  if (!validation.safe || !validation.resolvedUrl) {
    return NextResponse.json({ error: "Invalid or disallowed URL" }, { status: 400 })
  }

  try {
    const browserlessUrl = process.env.BROWSERLESS_URL || "http://browserless:3000/screenshot"
    const response = await fetch(browserlessUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: validation.resolvedUrl,
        setExtraHTTPHeaders: { "Host": validation.originalHostname },
        bestAttempt: true,
        addScriptTag: [
          {
            content: `
              // Remove GDPR/cookie consent modals before screenshot
              const selectors = [
                '[id*="cookie"]','[class*="cookie"]',
                '[id*="gdpr"]','[class*="gdpr"]',
                '[id*="consent"]','[class*="consent"]',
                '[id*="banner"]','[class*="banner"]',
                '[id*="popup"]','[class*="popup"]',
                '.cc-window','.CookieDeclaration',
                '#onetrust-banner-sdk','#CookieConsent',
                '#cookie-law-info-bar','#cookieChoiceInfo'
              ]
              selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                  const style = window.getComputedStyle(el)
                  if (style.position === 'fixed' || style.position === 'sticky') {
                    el.remove()
                  }
                })
              })
              document.body.style.overflow = 'auto'
            `
          }
        ],
        gotoOptions: {
          waitUntil: "networkidle",
        },
        options: { type: "jpeg", quality: 75, fullPage: false },
        viewport: { width: 1280, height: 800 },
        rejectResourceTypes: ["media", "font"],
      })
    })

    if (!response.ok) {
      console.warn(`Browserless warning for ${targetUrl}: ${response.status} ${response.statusText}`)
      return NextResponse.json({ error: "Failed to generate screenshot" }, { status: response.status >= 500 ? 502 : response.status })
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
