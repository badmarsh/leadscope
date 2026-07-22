/**
 * GET  /api/campaigns/[id]/settings  — read campaign settings (merged with defaults)
 * PUT  /api/campaigns/[id]/settings  — update campaign settings (allowlisted keys only)
 */
import { cookies } from "next/headers"
import { NextRequest, NextResponse } from "next/server"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"
import { queryOne } from "@/lib/db"
import { pool } from "@/lib/db"

// ── Allowlisted settings with defaults and validation rules ──────────────────
export const SETTINGS_SCHEMA: Record<
  string,
  { label: string; description: string; unit: string; default: number; min: number; max: number }
> = {
  search_cooldown_days: {
    label: "Search Cooldown",
    description: "Days before re-running the exact same search query against providers.",
    unit: "days",
    default: 30,
    min: 1,
    max: 365,
  },
  keyword_min_hits: {
    label: "Keyword Min Hits",
    description: "Minimum results from one search provider before trying the next in the waterfall.",
    unit: "results",
    default: 5,
    min: 1,
    max: 50,
  },
  max_enrichment_attempts: {
    label: "Max Enrichment Attempts",
    description: "Maximum Firecrawl scrape retries per candidate before marking as enrichment_failed.",
    unit: "attempts",
    default: 3,
    min: 1,
    max: 10,
  },
  enrichment_retry_hours: {
    label: "Enrichment Retry Window",
    description: "Hours to wait between Firecrawl retries for the same candidate.",
    unit: "hours",
    default: 24,
    min: 1,
    max: 168,
  },
  stale_reopen_days: {
    label: "Stale Reopen Window",
    description: "Days before a stale candidate can be re-discovered and reopened.",
    unit: "days",
    default: 90,
    min: 7,
    max: 365,
  },
  min_score_for_review: {
    label: "Min Score for Review",
    description: "Evaluation score cutoff (0-100) — candidates below this are auto-rejected.",
    unit: "score",
    default: 60,
    min: 0,
    max: 100,
  },
  evaluator_batch_size: {
    label: "Evaluator Batch Size",
    description: "Number of candidates to evaluate per Stage 3 run. Limits API backpressure.",
    unit: "candidates",
    default: 50,
    min: 1,
    max: 200,
  },
}

function mergeWithDefaults(stored: Record<string, number>): Record<string, number> {
  const result: Record<string, number> = {}
  for (const [key, schema] of Object.entries(SETTINGS_SCHEMA)) {
    result[key] = typeof stored[key] === "number" ? stored[key] : schema.default
  }
  return result
}

async function requireSession() {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  return session.loggedIn === true
}

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  if (!(await requireSession())) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { id } = await params
  const row = await queryOne<{ settings: Record<string, number>, business_brief: string | null }>(
    `SELECT COALESCE(settings, '{}') AS settings, business_brief FROM campaigns WHERE id = $1`,
    [id],
  )
  if (!row) return NextResponse.json({ error: "Campaign not found" }, { status: 404 })

  const settings = mergeWithDefaults(row.settings ?? {})
  return NextResponse.json({ settings, schema: SETTINGS_SCHEMA, business_brief: row.business_brief })
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  if (!(await requireSession())) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { id } = await params
  const body = await request.json()

  // Validate — only allowlisted keys, only integers within range
  const validated: Record<string, number> = {}
  const errors: string[] = []

  for (const [key, value] of Object.entries(body)) {
    if (key === 'business_brief') continue;

    const schema = SETTINGS_SCHEMA[key]
    if (!schema) {
      errors.push(`Unknown setting: '${key}'`)
      continue
    }
    const num = Number(value)
    if (!Number.isInteger(num)) {
      errors.push(`'${key}' must be an integer`)
      continue
    }
    if (num < schema.min || num > schema.max) {
      errors.push(`'${key}' must be between ${schema.min} and ${schema.max}`)
      continue
    }
    validated[key] = num
  }

  if (errors.length > 0) {
    return NextResponse.json({ error: errors.join("; ") }, { status: 400 })
  }

  const business_brief = body.business_brief

  if (business_brief !== undefined) {
    await pool.query(
      `UPDATE campaigns SET settings = $1::jsonb, business_brief = $2 WHERE id = $3`,
      [JSON.stringify(validated), business_brief, id],
    )
  } else {
    await pool.query(
      `UPDATE campaigns SET settings = $1::jsonb WHERE id = $2`,
      [JSON.stringify(validated), id],
    )
  }

  return NextResponse.json({ ok: true, settings: mergeWithDefaults(validated), business_brief })
}
