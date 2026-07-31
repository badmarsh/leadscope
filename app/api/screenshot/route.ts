import crypto from "crypto"
import dns from "dns"
import fs from "fs/promises"
import path from "path"
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

const CACHE_DIR = process.env.SCREENSHOT_CACHE_DIR || "/data/screenshots"
const CACHE_TTL_MS = 14 * 24 * 60 * 60 * 1000 // 14 days

export async function GET(request: NextRequest) {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { searchParams } = new URL(request.url)
  const targetUrl = searchParams.get("url")
  const refresh = searchParams.get("refresh") === "1"

  if (!targetUrl) {
    return NextResponse.json({ error: "Missing url parameter" }, { status: 400 })
  }

  const validation = await resolveSafeUrl(targetUrl)
  if (!validation.safe || !validation.resolvedUrl || !validation.originalHostname) {
    return NextResponse.json({ error: "Invalid or disallowed URL" }, { status: 400 })
  }

  const safeHostname = validation.originalHostname.toLowerCase().replace(/[^a-z0-9.-]/g, "_")
  const urlHash = crypto.createHash("sha256").update(targetUrl).digest("hex").substring(0, 10)
  const cacheFilePath = path.join(CACHE_DIR, `${safeHostname}_${urlHash}.jpg`)

  // Check fresh cache if not refreshing
  if (!refresh) {
    try {
      const stats = await fs.stat(cacheFilePath)
      if (Date.now() - stats.mtimeMs < CACHE_TTL_MS) {
        const cachedBuffer = await fs.readFile(cacheFilePath)
        return new NextResponse(cachedBuffer, {
          headers: {
            "Content-Type": "image/jpeg",
            "Cache-Control": "public, max-age=86400, stale-while-revalidate=43200",
          },
        })
      }
    } catch {
      // Cache file doesn't exist or stat failed, fall through to fetch
    }
  }

  const token = process.env.BROWSERLESS_TOKEN || "dev_browserless_token_change_in_prod"
  const defaultUrl = `http://browserless:3000/screenshot?token=${token}`
  const browserlessUrl = process.env.BROWSERLESS_URL || defaultUrl

  const payload = JSON.stringify({
    url: validation.resolvedUrl,
    setExtraHTTPHeaders: { Host: validation.originalHostname },
    extraHTTPHeaders: { Host: validation.originalHostname },
    gotoOptions: { waitUntil: "domcontentloaded", timeout: 15000 },
    waitForTimeout: 1200,
    blockConsentModals: true,
    addStyleTag: [
      {
        content: `#onetrust-consent-sdk,#onetrust-banner-sdk,#usercentrics-root,#CybotCookiebotDialog,#CybotCookiebotDialogBodyUnderlay,.qc-cmp2-container,[id^="sp_message_container"],#cookiescript_injected,.cc-window.cc-banner{display:none!important}html,body{overflow:auto!important}`,
      },
    ],
    bestAttempt: true,
    options: { type: "jpeg", quality: 75, fullPage: false },
    viewport: { width: 1280, height: 800 },
    rejectResourceTypes: ["media", "font"],
  })

  let lastResponse: Response | null = null
  let lastErrorText = ""

  // Attempt Browserless capture up to 2 times
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      if (attempt > 0) {
        await new Promise((res) => setTimeout(res, 500))
      }
      const response = await fetch(browserlessUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
      })

      if (response.ok) {
        const arrayBuffer = await response.arrayBuffer()
        const buffer = Buffer.from(arrayBuffer)

        // Asynchronously/atomically write to cache
        try {
          await fs.mkdir(CACHE_DIR, { recursive: true })
          const tempPath = `${cacheFilePath}.${Date.now()}.${Math.random().toString(36).substring(2)}.tmp`
          await fs.writeFile(tempPath, buffer)
          await fs.rename(tempPath, cacheFilePath)
        } catch (cacheErr) {
          console.warn("Screenshot cache write error:", cacheErr)
        }

        return new NextResponse(buffer, {
          headers: {
            "Content-Type": "image/jpeg",
            "Cache-Control": "public, max-age=86400, stale-while-revalidate=43200",
          },
        })
      } else {
        lastResponse = response
        try {
          lastErrorText = await response.text()
        } catch {
          lastErrorText = response.statusText
        }
        console.warn(`Browserless warning for ${targetUrl} (attempt ${attempt + 1}): ${response.status} ${response.statusText} - ${lastErrorText}`)
      }
    } catch (err) {
      console.warn(`Browserless fetch error for ${targetUrl} (attempt ${attempt + 1}):`, err)
      lastErrorText = String(err)
    }
  }

  // On failure of all attempts: return stale cache if available
  try {
    const staleBuffer = await fs.readFile(cacheFilePath)
    return new NextResponse(staleBuffer, {
      headers: {
        "Content-Type": "image/jpeg",
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=43200",
        "X-Screenshot-Stale": "true",
      },
    })
  } catch {
    // No stale cache available
  }

  const status = lastResponse ? (lastResponse.status >= 500 ? 502 : lastResponse.status) : 502
  return NextResponse.json({ error: "Failed to generate screenshot", details: lastErrorText }, { status })
}
