import { NextRequest, NextResponse } from "next/server"
import { query } from "@/lib/db"

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params
    const campaignId = parseInt(id)
    if (isNaN(campaignId)) return NextResponse.json({ error: "Invalid campaign ID" }, { status: 400 })

    const rows = await query(
      `SELECT id, domain, reason, added_at FROM do_not_contact WHERE campaign_id = $1 ORDER BY id DESC`,
      [campaignId]
    )
    return NextResponse.json({ exclusions: rows })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params
    const campaignId = parseInt(id)
    const body = await req.json()
    const { domain, reason } = body
    if (!domain) return NextResponse.json({ error: "Domain is required" }, { status: 400 })

    const rows = await query(
      `INSERT INTO do_not_contact (domain, campaign_id, reason)
       VALUES ($1, $2, $3) RETURNING *`,
      [domain, campaignId, reason || null]
    )
    return NextResponse.json({ exclusion: rows[0] })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id: paramId } = await params
    const campaignId = parseInt(paramId)
    const id = req.nextUrl.searchParams.get("id")
    if (!id) return NextResponse.json({ error: "Missing id" }, { status: 400 })

    await query(`DELETE FROM do_not_contact WHERE id = $1 AND campaign_id = $2`, [parseInt(id), campaignId])
    return NextResponse.json({ success: true })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
