import { NextResponse } from 'next/server'
import fs from 'fs/promises'
import path from 'path'

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const reportDir = searchParams.get('dir')
    const download = searchParams.get('download')

    const outputBaseDir = path.join(process.cwd(), 'seo-spam-hunter', 'output')

    let exists = false
    try {
      await fs.access(outputBaseDir)
      exists = true
    } catch {
      exists = false
    }

    if (!exists) {
      if (download === 'csv') {
        return new Response('No report available', { status: 404 })
      }
      return NextResponse.json({ reports: [], currentReport: null })
    }

    const entries = await fs.readdir(outputBaseDir, { withFileTypes: true })
    const subdirs = entries
      .filter((e) => e.isDirectory())
      .map((e) => e.name)
      .sort((a, b) => b.localeCompare(a))

    if (subdirs.length === 0) {
      if (download === 'csv') {
        return new Response('No report available', { status: 404 })
      }
      return NextResponse.json({ reports: [], currentReport: null })
    }

    const selectedDir = reportDir && subdirs.includes(reportDir) ? reportDir : subdirs[0]
    const dirPath = path.join(outputBaseDir, selectedDir)

    let csvContent = ''
    try {
      csvContent = await fs.readFile(path.join(dirPath, 'report.csv'), 'utf-8')
    } catch {}

    if (download === 'csv') {
      return new Response(csvContent, {
        headers: {
          'Content-Type': 'text/csv',
          'Content-Disposition': `attachment; filename="seo-spam-hunter-report-${selectedDir}.csv"`,
        },
      })
    }

    let markdown = ''
    let jsonContent: any = null

    try {
      markdown = await fs.readFile(path.join(dirPath, 'report.md'), 'utf-8')
    } catch {}

    try {
      const rawJson = await fs.readFile(path.join(dirPath, 'report.json'), 'utf-8')
      jsonContent = JSON.parse(rawJson)
    } catch {}

    return NextResponse.json({
      reports: subdirs,
      currentReport: {
        dir: selectedDir,
        markdown,
        json: jsonContent,
        csv: csvContent,
      },
    })
  } catch (error: any) {
    console.error('Failed to read seo-spam-hunter reports:', error)
    return NextResponse.json({ error: error.message || 'Failed to read reports' }, { status: 500 })
  }
}
