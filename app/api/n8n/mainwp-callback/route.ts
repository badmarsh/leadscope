import { NextRequest, NextResponse } from "next/server"
import { query } from "@/lib/db"
import { z } from "zod"

const callbackSchema = z.object({
  token: z.string(),
  status: z.enum(["email_sent", "plugin_downloaded", "plugin_installed", "converted"]),
  mainwp_site_id: z.string().optional()
})

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}))
  const parsed = callbackSchema.safeParse(body)
  
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid request", details: parsed.error }, { status: 400 })
  }
  
  const { token, status, mainwp_site_id } = parsed.data

  // Find the lead with this token
  const leads: any[] = await query(
    `SELECT candidate_id FROM leads WHERE mainwp_webhook_token = $1`,
    [token]
  )
  
  if (leads.length === 0) {
    return NextResponse.json({ error: "Invalid or expired token" }, { status: 401 })
  }
  
  const candidateId = leads[0].candidate_id
  
  // Update the appropriate timestamp
  const timestampField = `${status}_at`
  
  await query(
    `UPDATE leads SET 
      ${timestampField} = now(),
      mainwp_site_id = COALESCE($1, mainwp_site_id)
     WHERE candidate_id = $2`,
    [mainwp_site_id ?? null, candidateId]
  )
  
  // If converted, we might want to nullify the token or update candidate status
  if (status === "converted") {
    await query(`UPDATE candidates SET status = 'converted' WHERE id = $1`, [candidateId])
    await query(`UPDATE leads SET mainwp_webhook_token = NULL WHERE candidate_id = $1`, [candidateId])
  }

  return NextResponse.json({ ok: true })
}
