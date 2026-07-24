import { NextResponse } from 'next/server'
import fs from 'fs/promises'
import path from 'path'

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const campaignId = searchParams.get('campaignId')

    const findingsPath = path.join(process.cwd(), 'wp-hunter', 'findings.jsonl')
    
    let exists = false
    try {
      await fs.access(findingsPath)
      exists = true
    } catch {
      exists = false
    }

    if (!exists) {
      return NextResponse.json({ findings: [] })
    }

    const content = await fs.readFile(findingsPath, 'utf-8')
    const lines = content.split('\n').filter((l) => l.trim().length > 0)
    
    let findings = lines.map((l) => JSON.parse(l))

    if (campaignId) {
      findings = findings.filter((f) => f.campaign_id === campaignId)
    }

    return NextResponse.json({ findings })
  } catch (error: any) {
    console.error('Failed to read wp-hunter findings:', error)
    return NextResponse.json({ error: error.message || 'Failed to read findings' }, { status: 500 })
  }
}
