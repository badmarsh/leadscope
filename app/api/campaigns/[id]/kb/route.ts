import { cookies } from "next/headers"
import { NextRequest, NextResponse } from "next/server"
import { getIronSession } from "iron-session"
import { sessionOptions, type SessionData } from "@/lib/session"
import { query } from "@/lib/db"

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
  
  const signatures = await query(
    `SELECT id, snippet, malware_family, source_url, confidence, added_at 
     FROM malware_signatures 
     WHERE campaign_id = $1 
     ORDER BY added_at DESC`,
    [id]
  )

  return NextResponse.json({ signatures })
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  if (!(await requireSession())) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { id } = await params
  const { snippet, malware_family, source_url, confidence } = await request.json()

  if (!snippet) {
    return NextResponse.json({ error: "Snippet is required" }, { status: 400 })
  }

  try {
    const result = await query(
      `INSERT INTO malware_signatures (campaign_id, snippet, malware_family, source_url, confidence)
       VALUES ($1, $2, $3, $4, $5)
       RETURNING id, snippet, malware_family, source_url, confidence, added_at`,
      [id, snippet, malware_family ?? "Unknown", source_url ?? null, confidence ?? "medium"]
    )
    return NextResponse.json({ signature: result[0] })
  } catch (err: any) {
    if (err.code === '23505') { // unique violation
      return NextResponse.json({ error: "Signature already exists for this campaign" }, { status: 400 })
    }
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  if (!(await requireSession())) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { id: campaign_id } = await params
  const { id, snippet, malware_family, source_url, confidence } = await request.json()

  if (!id || !snippet) {
    return NextResponse.json({ error: "ID and Snippet are required" }, { status: 400 })
  }

  try {
    const result = await query(
      `UPDATE malware_signatures 
       SET snippet = $1, malware_family = $2, source_url = $3, confidence = $4
       WHERE id = $5 AND campaign_id = $6
       RETURNING id, snippet, malware_family, source_url, confidence, added_at`,
      [snippet, malware_family ?? "Unknown", source_url ?? null, confidence ?? "medium", id, campaign_id]
    )
    
    if (result.length === 0) {
        return NextResponse.json({ error: "Signature not found" }, { status: 404 })
    }
    
    return NextResponse.json({ signature: result[0] })
  } catch (err: any) {
    if (err.code === '23505') { // unique violation
      return NextResponse.json({ error: "Another signature with this snippet already exists" }, { status: 400 })
    }
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  if (!(await requireSession())) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { id: campaign_id } = await params
  const sig_id = request.nextUrl.searchParams.get("sig_id")

  if (!sig_id) {
    return NextResponse.json({ error: "sig_id is required" }, { status: 400 })
  }

  await query(
    `DELETE FROM malware_signatures WHERE id = $1 AND campaign_id = $2`,
    [sig_id, campaign_id]
  )

  return NextResponse.json({ ok: true })
}
