"use client"

import React, { useMemo } from "react"
import { Download, FileText, BarChart3, Database, Layers } from "lucide-react"

export interface ReportData {
  dir: string
  markdown: string
  json: any[]
  csv: string
}

interface ReportViewerProps {
  reportList: string[]
  currentReport: ReportData | null
  onSelectReportDir: (dir: string) => void
  pipeline: "wp-hunter" | "seo-spam-hunter"
}

export function ReportViewer({
  reportList,
  currentReport,
  onSelectReportDir,
  pipeline,
}: ReportViewerProps) {
  const sortedReports = useMemo(() => {
    return [...reportList].sort((a, b) => b.localeCompare(a))
  }, [reportList])

  // Stats bar calculation from currentReport.json
  const stats = useMemo(() => {
    if (!currentReport?.json || !Array.isArray(currentReport.json)) {
      return null
    }

    const json = currentReport.json
    let total = json.length
    let confirmed = 0
    let candidates = 0
    let stale = 0
    const sourcesSet = new Set<string>()

    for (const item of json) {
      if (item.confidence === "confirmed") confirmed++
      else candidates++

      if (item.is_stale) stale++

      if (item.source) sourcesSet.add(item.source)
      if (Array.isArray(item.sources)) {
        item.sources.forEach((s: string) => sourcesSet.add(s))
      }
    }

    return {
      total,
      confirmed,
      candidates,
      stale,
      sources: Array.from(sourcesSet),
    }
  }, [currentReport])

  const handleDownloadCsv = () => {
    if (!currentReport?.dir) return
    const downloadUrl = `/api/${pipeline}/reports?dir=${encodeURIComponent(
      currentReport.dir
    )}&download=csv`
    window.open(downloadUrl, "_blank")
  }

  return (
    <div className="space-y-4">
      {/* Selector & Download Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex size-8 items-center justify-center rounded-lg bg-amber-500/15 text-amber-600 dark:text-amber-400">
            <FileText className="size-4" />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Select Historical Report Run
            </label>
            <select
              value={currentReport?.dir || ""}
              onChange={(e) => onSelectReportDir(e.target.value)}
              className="mt-0.5 rounded-md border border-input bg-background px-3 py-1 font-mono text-xs font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {sortedReports.length === 0 ? (
                <option value="">No generated reports yet</option>
              ) : (
                sortedReports.map((dir) => (
                  <option key={dir} value={dir}>
                    {dir}
                  </option>
                ))
              )}
            </select>
          </div>
        </div>

        <button
          onClick={handleDownloadCsv}
          disabled={!currentReport}
          className="flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2 text-xs font-semibold text-foreground shadow-sm hover:bg-accent transition-colors disabled:opacity-50"
        >
          <Download className="size-3.5 text-primary" />
          <span>Download CSV Report</span>
        </button>
      </div>

      {/* Stats Bar */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <div className="rounded-xl border border-border bg-card p-3 shadow-sm space-y-1">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase">Total Domains</span>
            <div className="text-base font-bold font-mono text-foreground">{stats.total}</div>
          </div>
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 shadow-sm space-y-1">
            <span className="text-[10px] font-semibold text-red-600 dark:text-red-400 uppercase">Confirmed</span>
            <div className="text-base font-bold font-mono text-red-600 dark:text-red-400">{stats.confirmed}</div>
          </div>
          <div className="rounded-xl border border-slate-500/30 bg-slate-500/10 p-3 shadow-sm space-y-1">
            <span className="text-[10px] font-semibold text-slate-600 dark:text-slate-400 uppercase">Candidates</span>
            <div className="text-base font-bold font-mono text-slate-600 dark:text-slate-400">{stats.candidates}</div>
          </div>
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 shadow-sm space-y-1">
            <span className="text-[10px] font-semibold text-amber-600 dark:text-amber-400 uppercase">Stale</span>
            <div className="text-base font-bold font-mono text-amber-600 dark:text-amber-400">{stats.stale}</div>
          </div>
          <div className="rounded-xl border border-border bg-card p-3 shadow-sm space-y-1 col-span-2 sm:col-span-1">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase">Sources Included</span>
            <div className="text-xs font-mono font-medium text-foreground truncate">
              {stats.sources.length > 0 ? stats.sources.join(", ") : "N/A"}
            </div>
          </div>
        </div>
      )}

      {/* Markdown Content Display */}
      {currentReport?.markdown ? (
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <span className="font-semibold text-xs text-foreground flex items-center gap-1.5">
              <FileText className="size-3.5 text-primary" />
              <span>Report Markdown Preview ({currentReport.dir})</span>
            </span>
          </div>
          <pre className="max-h-[500px] overflow-y-auto rounded-lg bg-muted/50 p-4 font-mono text-xs leading-relaxed text-foreground whitespace-pre-wrap">
            {currentReport.markdown}
          </pre>
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-border p-8 text-center text-xs text-muted-foreground">
          No report selected or report content is empty. Run &quot;Stage C: Generate Report Only&quot; to generate a new report.
        </div>
      )}
    </div>
  )
}
