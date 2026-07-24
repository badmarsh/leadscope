import { NextResponse } from 'next/server'
import { exec } from 'child_process'
import { promisify } from 'util'
import path from 'path'

const execAsync = promisify(exec)

export async function GET() {
  try {
    const cwd = path.join(process.cwd(), 'seo-spam-hunter')
    const pythonCmd = `python3 -c "import json, yaml, sys; from datetime import datetime, date; from pathlib import Path; f = Path('campaigns.yaml'); data = yaml.safe_load(f.read_text()); today = date.today(); res = []; [res.append(dict(c, added=str(c.get('added')), days_old=(today - (c.get('added') if isinstance(c.get('added'), date) else today)).days, is_stale=(today - (c.get('added') if isinstance(c.get('added'), date) else today)).days > c.get('stale_after_days', 30), is_template=bool(c.get('publicwww_query') and '{{' in c.get('publicwww_query')))) for c in data.get('campaigns', [])]; print(json.dumps(res))"`

    const { stdout } = await execAsync(pythonCmd, { cwd })
    const campaigns = JSON.parse(stdout.trim())

    return NextResponse.json({ campaigns })
  } catch (error: any) {
    console.error('Failed to load campaigns:', error)
    return NextResponse.json({ error: error.message || 'Failed to load campaigns' }, { status: 500 })
  }
}
