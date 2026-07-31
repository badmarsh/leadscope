import { NextResponse } from 'next/server'
import { exec, spawn, execFile } from 'child_process'
import { promisify } from 'util'
import path from 'path'
import fs from 'fs/promises'

const execAsync = promisify(exec)
const execFileAsync = promisify(execFile)

function getPythonBin() {
  return process.platform === 'win32' ? 'python' : 'python3'
}

function buildCliArgs(stage: string, campaignId: string, options: {
  tempFilePath?: string | null
  forceStale?: boolean
  vtPivotDomains?: boolean
  vtGraph?: boolean
}): string[] {
  const args = ['-m', 'seo_spam_hunter.cli']

  switch (stage) {
    case 'ingest':
      args.push('ingest', '--campaign', campaignId)
      if (options.tempFilePath) {
        args.push('--file', options.tempFilePath)
      }
      break

    case 'ingest-feeds':
      args.push('ingest-feeds', '--campaign', campaignId)
      break

    case 'ct-monitor':
      args.push('ct-monitor', '--campaign', campaignId, '--max-events', '50')
      break

    case 'pivot':
      args.push('pivot', '--campaign', campaignId)
      if (options.vtPivotDomains) {
        args.push('--vt-pivot-domains')
      }
      if (options.vtGraph) {
        args.push('--vt-graph')
      }
      break

    case 'report':
      args.push('report', '--campaign', campaignId)
      break

    case 'run':
      args.push('run', '--campaign', campaignId)
      if (options.tempFilePath) {
        args.push('--file', options.tempFilePath)
      }
      if (options.forceStale) {
        args.push('--i-know-this-is-stale')
      }
      break

    default:
      throw new Error(`Unknown stage: ${stage}`)
  }

  return args
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const stage = searchParams.get('stage')
  const campaignId = searchParams.get('campaignId')
  const forceStale = searchParams.get('forceStale') === 'true'
  const vtPivotDomains = searchParams.get('vtPivotDomains') === 'true'
  const vtGraph = searchParams.get('vtGraph') === 'true'
  const pasteContent = searchParams.get('pasteContent')

  if (!stage || !campaignId) {
    return NextResponse.json({ error: 'Missing required parameters: stage, campaignId' }, { status: 400 })
  }
  if (!/^[a-zA-Z0-9_-]+$/.test(stage) || !/^[a-zA-Z0-9_-]+$/.test(campaignId)) {
    return NextResponse.json({ error: 'Invalid parameters: stage and campaignId must be alphanumeric strings' }, { status: 400 })
  }

  const cwd = path.join(process.cwd(), 'seo-spam-hunter')
  let tempFilePath: string | null = null

  if (pasteContent && pasteContent.trim().length > 0) {
    tempFilePath = path.join(cwd, `temp_ingest_${Date.now()}.txt`)
    await fs.writeFile(tempFilePath, pasteContent.trim(), 'utf-8')
  }

  let args: string[]
  try {
    args = buildCliArgs(stage, campaignId, { tempFilePath, forceStale, vtPivotDomains, vtGraph })
  } catch (err: any) {
    if (tempFilePath) await fs.unlink(tempFilePath).catch(() => {})
    return NextResponse.json({ error: err.message }, { status: 400 })
  }

  const encoder = new TextEncoder()

  const stream = new ReadableStream({
    start(controller) {
      const pyBin = getPythonBin()
      const proc = spawn(pyBin, args, { 
        cwd,
        env: { ...process.env, PYTHONPATH: path.join(cwd, 'src') }
      })

      proc.stdout.on('data', (chunk) => {
        const lines = chunk.toString().split('\n')
        for (const line of lines) {
          if (line) {
            controller.enqueue(encoder.encode(`data: ${line}\n\n`))
          }
        }
      })

      proc.stderr.on('data', (chunk) => {
        const lines = chunk.toString().split('\n')
        for (const line of lines) {
          if (line) {
            controller.enqueue(encoder.encode(`data: ${line}\n\n`))
          }
        }
      })

      proc.on('error', (err) => {
        controller.enqueue(encoder.encode(`data: [ERROR] ${err.message}\n\n`))
      })

      proc.on('close', async () => {
        if (tempFilePath) {
          await fs.unlink(tempFilePath).catch(() => {})
        }

        if (stage === 'ingest' || stage === 'ingest-feeds') {
           try {
             controller.enqueue(encoder.encode('data: [INFO] Running database ingest...\n\n'))
             await execFileAsync(getPythonBin(), ['services/jobs/ingest_hunters.py'], { cwd: process.cwd() })
             controller.enqueue(encoder.encode('data: [INFO] Database ingest complete\n\n'))
           } catch (e: any) {
             controller.enqueue(encoder.encode(`data: [ERROR] Ingest failed: ${e.message}\n\n`))
           }
        }

        controller.enqueue(encoder.encode('data: [DONE]\n\n'))
        controller.close()
      })
    },
  })

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      'Connection': 'keep-alive',
    },
  })
}

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const { stage, campaignId, pasteContent, forceStale, vtPivotDomains, vtGraph } = body

    if (!stage || !campaignId) {
      return NextResponse.json({ error: 'Missing required parameters: stage, campaignId' }, { status: 400 })
    }
    if (!/^[a-zA-Z0-9_-]+$/.test(stage) || !/^[a-zA-Z0-9_-]+$/.test(campaignId)) {
      return NextResponse.json({ error: 'Invalid parameters: stage and campaignId must be alphanumeric strings' }, { status: 400 })
    }

    const cwd = path.join(process.cwd(), 'seo-spam-hunter')
    let tempFilePath: string | null = null

    if (pasteContent && pasteContent.trim().length > 0) {
      tempFilePath = path.join(cwd, `temp_ingest_${Date.now()}.txt`)
      await fs.writeFile(tempFilePath, pasteContent.trim(), 'utf-8')
    }

    let args: string[]
    try {
      args = buildCliArgs(stage, campaignId, { tempFilePath, forceStale, vtPivotDomains, vtGraph })
    } catch (err: any) {
      if (tempFilePath) await fs.unlink(tempFilePath).catch(() => {})
      return NextResponse.json({ error: err.message }, { status: 400 })
    }

    const { stdout, stderr } = await execFileAsync(getPythonBin(), args, { 
      cwd, 
      timeout: 120000,
      env: { ...process.env, PYTHONPATH: path.join(cwd, 'src') }
    }).catch((err: any) => {
      return { stdout: err.stdout || '', stderr: err.stderr || err.message }
    })

    if (tempFilePath) {
      await fs.unlink(tempFilePath).catch(() => {})
    }

    const outputLogs = (stdout + '\n' + stderr).trim()

    let ingestLogs = ''
    if (stage === 'ingest' || stage === 'ingest-feeds') {
      try {
        const { stdout: ingestOut, stderr: ingestErr } = await execFileAsync(getPythonBin(), ['services/jobs/ingest_hunters.py'], { cwd: process.cwd() })
        ingestLogs = '\n\n[DATABASE INGEST]\n' + ingestOut + '\n' + ingestErr
      } catch (e: any) {
        ingestLogs = `\n\n[DATABASE INGEST ERROR] ${e.message}`
      }
    }

    return NextResponse.json({
      success: true,
      stage,
      campaignId,
      logs: outputLogs + ingestLogs,
    })
  } catch (error: any) {
    console.error('Error executing seo-spam-hunter pipeline:', error)
    return NextResponse.json({ error: error.message || 'Pipeline execution failed' }, { status: 500 })
  }
}
