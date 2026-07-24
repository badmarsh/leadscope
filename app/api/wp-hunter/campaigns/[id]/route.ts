import { NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs/promises'
import * as yaml from 'js-yaml'

const YAML_PATH = path.join(process.cwd(), 'wp-hunter', 'campaigns.yaml')

async function readCampaignsYaml(): Promise<any> {
  const content = await fs.readFile(YAML_PATH, 'utf-8')
  return yaml.load(content) || { campaigns: [] }
}

async function writeCampaignsYaml(data: any): Promise<void> {
  const content = yaml.dump(data, { indent: 2, lineWidth: -1 })
  await fs.writeFile(YAML_PATH, content, 'utf-8')
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const doc: any = await readCampaignsYaml()
    const campaigns = doc.campaigns || []
    const campaign = campaigns.find((c: any) => c.id === id)

    if (!campaign) {
      return NextResponse.json({ error: `Campaign '${id}' not found` }, { status: 404 })
    }

    return NextResponse.json({ campaign })
  } catch (error: any) {
    return NextResponse.json({ error: error.message || 'Failed to fetch campaign' }, { status: 500 })
  }
}

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body = await request.json()

    const doc: any = await readCampaignsYaml()
    const campaigns = doc.campaigns || []
    const campaignIndex = campaigns.findIndex((c: any) => c.id === id)

    if (campaignIndex === -1) {
      return NextResponse.json({ error: `Campaign '${id}' not found` }, { status: 404 })
    }

    const campaign = campaigns[campaignIndex]

    // Allowed fields whitelist
    if (body.name !== undefined) campaign.name = body.name
    if (body.notes !== undefined) campaign.notes = body.notes
    if (body.stale_after_days !== undefined) campaign.stale_after_days = Number(body.stale_after_days)
    if (body.urlscan_pivot !== undefined) campaign.urlscan_pivot = Array.isArray(body.urlscan_pivot) ? body.urlscan_pivot : []
    if (body.publicwww_query !== undefined) campaign.publicwww_query = body.publicwww_query

    campaigns[campaignIndex] = campaign
    doc.campaigns = campaigns

    await writeCampaignsYaml(doc)

    return NextResponse.json({ success: true, campaign })
  } catch (error: any) {
    console.error('Error updating wp-hunter campaign:', error)
    return NextResponse.json({ error: error.message || 'Failed to update campaign' }, { status: 500 })
  }
}
