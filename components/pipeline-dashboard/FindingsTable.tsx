"use client"

import React, { useMemo, useState } from "react"
import { ExternalLink, ShieldCheck, ShieldAlert, AlertCircle } from "lucide-react"
import { SourceLegend } from "./SourceLegend"

export interface RawFinding {
  domain: string
  rank?: number | null
  snippet?: string | null
  visible?: boolean
  campaign_id?: string
  ingested_at?: string
  source: string
  confidence?: string
  in_urlscan?: boolean
  in_vt?: boolean
}

export interface MergedFinding {
  domain: string
  sources: string[]
  confidence: string
  ingested_at: string
  rank: number | null
  snippet: string | null
  visible: boolean
}

interface FindingsTableProps {
  findings: RawFinding[]
  selectedCampaignId?: string
}

export function FindingsTable({ findings, selectedCampaignId }: FindingsTableProps) {
  const [activeSource, setActiveSource] = useState<string>("all")
  const [tierFilter, setTierFilter] = useState<string>("all")

  // Client-side domain merge
  const mergedFindings = useMemo(() => {
    const map = new Map<string, MergedFinding>()

    for (const f of findings) {
      if (selectedCampaignId && f.campaign_id && f.campaign_id !== selectedCampaignId) {
        continue
      }

      const existing = map.get(f.domain)
      if (existing) {
        if (!existing.sources.includes(f.source)) {
          existing.sources.push(f.source)
        }
        if (f.confidence === "confirmed") {
          existing.confidence = "confirmed"
        } else if (f.confidence === "abusech_candidate" && existing.confidence !== "confirmed") {
          existing.confidence = "abusech_candidate"
        }
        if (f.rank && (!existing.rank || f.rank < existing.rank)) {
          existing.rank = f.rank
        }
        if (f.snippet && !existing.snippet) {
          existing.snippet = f.snippet
        }
      } else {
        map.set(f.domain, {
          domain: f.domain,
          sources: [f.source],
          confidence: f.confidence || "candidate",
          ingested_at: f.ingested_at || new Date().toISOString(),
          rank: f.rank ?? null,
          snippet: f.snippet ?? null,
          visible: f.visible !== false,
        })
      }
    }

    return Array.from(map.values()).sort((a, b) => a.domain.localeCompare(b.domain))
  }, [findings, selectedCampaignId])

  // Count distinct sources for legend badges
  const sourceCounts = useMemo(() => {
    const counts: Record<string, number> = { all: mergedFindings.length }
    for (const f of mergedFindings) {
      for (const s of f.sources) {
        const key = s === "virustotal_graph" ? "virustotal" : s
        counts[key] = (counts[key] || 0) + 1
      }
    }
    return counts
  }, [mergedFindings])

  // Filter merged findings by activeSource & tierFilter
  const filteredFindings = useMemo(() => {
    return mergedFindings.filter((item) => {
      if (activeSource !== "all") {
        const matchesSource = item.sources.some((s) => {
          if (activeSource === "virustotal") return s === "virustotal" || s === "virustotal_graph"
          return s === activeSource
        })
        if (!matchesSource) return false
      }
      if (tierFilter !== "all" && item.confidence !== tierFilter) {
        return false
      }
      return true
    })
  }, [mergedFindings, activeSource, tierFilter])

  const renderSourceBadge = (src: string) => {
    switch (src) {
      case "urlhaus":
        return (
          <span key={src} className="rounded bg-cyan-500/15 border border-cyan-500/30 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-cyan-600 dark:text-cyan-400">
            URLhaus
          </span>
        )
      case "threatfox":
        return (
          <span key={src} className="rounded bg-red-500/15 border border-red-500/30 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-red-600 dark:text-red-400">
            ThreatFox
          </span>
        )
      case "virustotal":
      case "virustotal_graph":
        return (
          <span key={src} className="rounded bg-blue-500/15 border border-blue-500/30 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-blue-600 dark:text-blue-400">
            {src === "virustotal_graph" ? "VT Graph" : "VirusTotal"}
          </span>
        )
      case "urlscan":
        return (
          <span key={src} className="rounded bg-purple-500/15 border border-purple-500/30 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-purple-600 dark:text-purple-400">
            urlscan
          </span>
        )
      case "publicwww":
        return (
          <span key={src} className="rounded bg-emerald-500/15 border border-emerald-500/30 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
            PublicWWW
          </span>
        )
      case "certstream":
        return (
          <span key={src} className="rounded bg-violet-500/15 border border-violet-500/30 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-violet-600 dark:text-violet-400">
            CT Stream
          </span>
        )
      default:
        return (
          <span key={src} className="rounded bg-muted border border-border px-1.5 py-0.5 font-mono text-[10px] font-semibold text-muted-foreground">
            {src}
          </span>
        )
    }
  }

  const renderConfidenceBadge = (confidence: string) => {
    switch (confidence) {
      case "confirmed":
        return (
          <span className="inline-flex items-center gap-1 rounded bg-red-500/15 border border-red-500/30 px-2 py-0.5 font-mono text-[10px] font-bold text-red-600 dark:text-red-400">
            <ShieldAlert className="size-3" /> CONFIRMED
          </span>
        )
      case "abusech_candidate":
        return (
          <span className="inline-flex items-center gap-1 rounded bg-amber-500/15 border border-amber-500/30 px-2 py-0.5 font-mono text-[10px] font-semibold text-amber-700 dark:text-amber-400">
            <ShieldCheck className="size-3" /> ABUSE.CH
          </span>
        )
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded bg-slate-500/15 border border-slate-500/30 px-2 py-0.5 font-mono text-[10px] font-medium text-slate-600 dark:text-slate-400">
            <AlertCircle className="size-3" /> CANDIDATE
          </span>
        )
    }
  }

  return (
    <div className="space-y-4">
      {/* Legend & Tier Filters Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card p-3 shadow-sm">
        <SourceLegend
          activeSource={activeSource}
          onSelectSource={setActiveSource}
          sourceCounts={sourceCounts}
        />

        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">Tier:</span>
          <select
            value={tierFilter}
            onChange={(e) => setTierFilter(e.target.value)}
            className="rounded-md border border-input bg-background px-2.5 py-1 text-xs font-medium text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="all">All Tiers</option>
            <option value="confirmed">Confirmed</option>
            <option value="abusech_candidate">Abuse.ch Candidate</option>
            <option value="candidate">Candidate</option>
          </select>
        </div>
      </div>

      {/* Findings Table */}
      <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-border bg-muted/60 text-muted-foreground font-semibold">
              <tr>
                <th className="px-4 py-3">Domain</th>
                <th className="px-4 py-3">Confidence Tier</th>
                <th className="px-4 py-3">Sources</th>
                <th className="px-4 py-3">PublicWWW Rank</th>
                <th className="px-4 py-3 text-right">External OSINT Lookup</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredFindings.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                    No findings match the current filter criteria.
                  </td>
                </tr>
              ) : (
                filteredFindings.map((item) => (
                  <tr key={item.domain} className="hover:bg-accent/40 transition-colors">
                    <td className="px-4 py-3 font-mono font-bold text-foreground">
                      {item.domain}
                    </td>
                    <td className="px-4 py-3">
                      {renderConfidenceBadge(item.confidence)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {item.sources.map((s) => renderSourceBadge(s))}
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-muted-foreground">
                      {item.rank ? `#${item.rank.toLocaleString()}` : "N/A"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <a
                          href={`https://urlscan.io/search/#domain:${item.domain}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          title="urlscan.io lookup"
                          className="rounded px-2 py-0.5 border border-purple-500/30 bg-purple-500/10 text-purple-600 dark:text-purple-400 hover:bg-purple-500/20 text-[10px] font-semibold transition-colors inline-flex items-center gap-1"
                        >
                          <span>urlscan</span>
                          <ExternalLink className="size-2.5" />
                        </a>
                        <a
                          href={`https://www.virustotal.com/gui/domain/${item.domain}/detection`}
                          target="_blank"
                          rel="noopener noreferrer"
                          title="VirusTotal lookup"
                          className="rounded px-2 py-0.5 border border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20 text-[10px] font-semibold transition-colors inline-flex items-center gap-1"
                        >
                          <span>VT</span>
                          <ExternalLink className="size-2.5" />
                        </a>
                        <a
                          href={`https://check.certstream.info/?q=${item.domain}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          title="CertStream lookup"
                          className="rounded px-2 py-0.5 border border-violet-500/30 bg-violet-500/10 text-violet-600 dark:text-violet-400 hover:bg-violet-500/20 text-[10px] font-semibold transition-colors inline-flex items-center gap-1"
                        >
                          <span>CT</span>
                          <ExternalLink className="size-2.5" />
                        </a>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
