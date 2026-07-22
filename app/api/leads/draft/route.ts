import { NextResponse } from "next/server"
import { cookies } from "next/headers"
import { getIronSession } from "iron-session"
import { query } from "@/lib/db"
import { sessionOptions, SessionData } from "@/lib/session"
import { chatText } from "@/lib/llm"

export async function POST(req: Request) {
  const session = await getIronSession<SessionData>(await cookies(), sessionOptions)
  if (!session.loggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  try {
    const { leadId } = await req.json()
    if (!leadId) {
      return NextResponse.json({ error: "Missing leadId" }, { status: 400 })
    }

    // 1. Fetch lead, evaluation, feedback, and campaign brief
    const rows = await query(`
      SELECT 
        l.id as lead_id,
        l.draft_email,
        c.company_name,
        c.domain,
        e.rationale,
        f.note as feedback_note,
        camp.business_brief,
        camp.name as campaign_name
      FROM leads l
      JOIN candidates c ON l.candidate_id = c.id
      LEFT JOIN evaluations e ON e.candidate_id = c.id
      LEFT JOIN feedback f ON f.candidate_id = c.id
      JOIN campaigns camp ON l.campaign_id = camp.id
      WHERE l.id = $1
    `, [leadId])

    if (rows.length === 0) {
      return NextResponse.json({ error: "Lead not found" }, { status: 404 })
    }

    const lead = rows[0] as Record<string, unknown>

    // 2. If already generated, return it
    if (lead.draft_email) {
      return NextResponse.json({ draftEmail: lead.draft_email })
    }

    if (!lead.business_brief) {
      return NextResponse.json({ error: "Campaign is missing a business brief. Cannot generate draft." }, { status: 400 })
    }

    // 3. Construct prompt
    const prompt = `You are an expert SDR (Sales Development Representative).
Your task is to write a highly personalized, concise cold outreach email to ${lead.company_name} (${lead.domain}).

Campaign/Product Context:
${lead.business_brief}

Why we selected this prospect (Evaluation Rationale):
${lead.rationale || "N/A"}

Reviewer Note:
${lead.feedback_note || "N/A"}

Write a short, engaging email (max 4-5 sentences) that hooks the reader, references our reason for reaching out based on their evaluation, and includes a soft call to action. Keep it professional but conversational. Do not include subject line in the output, just the email body.
Please write the email in Slovak language as requested by the user previously.`

    // 4. Call shared LLM client
    const { text: draftContent } = await chatText(
      prompt,
      "You are a professional B2B salesperson writing outreach emails.",
      { temperature: 0.7 },
    )

    if (!draftContent) {
      return NextResponse.json({ error: "Empty response from AI provider" }, { status: 502 })
    }

    // 5. Save to database
    await query(`
      UPDATE leads SET draft_email = $1, updated_at = now() WHERE id = $2
    `, [draftContent, leadId])

    return NextResponse.json({ draftEmail: draftContent })
  } catch (err) {
    console.error("Error generating draft email:", err instanceof Error ? err.message : err)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}

