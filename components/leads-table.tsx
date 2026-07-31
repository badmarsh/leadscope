"use client"

import { useMemo, useState, useEffect } from "react"
import { ArrowDown, ArrowUp, ArrowUpDown, ExternalLink, Inbox, Search } from "lucide-react"
import type { Lead, CampaignId } from "@/lib/leads-data"
import { formatDate, scoreColorClasses, statusBadgeClasses, statusLabels, getLeadMissingFields, isLeadComplete } from "@/lib/status"
import { cn } from "@/lib/utils"
import { useTranslation } from "@/lib/i18n"

type SortKey = "company" | "domain" | "score" | "status" | "dateFound"
type PipelineSortKey = "domain" | "source" | "status" | "date"
type SortDir = "asc" | "desc"
type ViewFilter = "for_review" | "approved" | "discarded" | "rejected" | "pipeline"

interface RawCandidate {
  id: number
  domain: string
  company_name: string | null
  source: string
  status: string
  created_at: string
  last_seen_at?: string
  enrichment_attempt_count: number
}

interface LeadsTableProps {
  leads: Lead[]
  selectedId: string | null
  onSelect: (lead: Lead) => void
  onFilteredChange?: (leads: Lead[]) => void
  onBulkAction?: (ids: string[], action: "approved" | "rejected" | "junk" | "rerun_evaluation" | "rerun_enrichment") => Promise<void>
  activeCampaign?: CampaignId
  rawCandidates?: RawCandidate[]
}

export function LeadsTable({ leads, selectedId, onSelect, onFilteredChange, onBulkAction, activeCampaign, rawCandidates = [] }: LeadsTableProps) {
  const { t } = useTranslation()

  const columns: { key: SortKey; label: string; className?: string }[] = [
    { key: "company", label: t("leads_table.columns.company", { defaultValue: "Company" }) },
    { key: "domain", label: t("leads_table.columns.domain", { defaultValue: "Domain" }) },
    { key: "score", label: t("leads_table.columns.score", { defaultValue: "Score" }), className: "w-36" },
    { key: "status", label: t("leads_table.columns.status", { defaultValue: "Status" }), className: "w-32" },
    { key: "dateFound", label: t("leads_table.columns.date_found", { defaultValue: "Date found" }), className: "w-32" },
  ]

  const emptyStates: Record<"for_review"|"approved"|"discarded"|"rejected", { heading: string; sub: string }> = {
    for_review: {
      heading: t("leads_table.empty.for_review.heading", { defaultValue: "Queue is empty — great work!" }),
      sub: t("leads_table.empty.for_review.sub", { defaultValue: "All evaluated leads have been reviewed or decided." }),
    },
    approved: {
      heading: t("leads_table.empty.approved.heading", { defaultValue: "No approved leads yet" }),
      sub: t("leads_table.empty.approved.sub", { defaultValue: "Approve leads from the review queue to see them here." }),
    },
    discarded: {
      heading: t("leads_table.empty.discarded.heading", { defaultValue: "No discarded leads" }),
      sub: t("leads_table.empty.discarded.sub", { defaultValue: "No invalid or discarded candidates found." }),
    },
    rejected: {
      heading: t("leads_table.empty.rejected.heading", { defaultValue: "No rejected leads" }),
      sub: t("leads_table.empty.rejected.sub", { defaultValue: "No rejected or junk leads found." }),
    },
  }

  const [view, setView] = useState<ViewFilter>("for_review")
  const [sortKey, setSortKey] = useState<SortKey>("score")
  const [sortDir, setSortDir] = useState<SortDir>("desc")
  const [search, setSearch] = useState("")
  const [scoreFilter, setScoreFilter] = useState<'all'|'high'|'med'|'low'>('all')
  const [signatureFilter, setSignatureFilter] = useState<string>('all')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [isBulkActing, setIsBulkActing] = useState(false)
  const [pipelineSortKey, setPipelineSortKey] = useState<PipelineSortKey>("date")
  const [pipelineSortDir, setPipelineSortDir] = useState<SortDir>("desc")
  const [pipelineStatusFilter, setPipelineStatusFilter] = useState<string>("all")

  const availableSignatures = useMemo(() => {
    const INVALID_NAMES = new Set(["none", "n/a", "unknown", "null", "undefined", ""])
    const families = new Set<string>()
    for (const l of leads) {
      if (l.evidence.kind === "malware" && l.evidence.malwareFamily) {
        const raw = l.evidence.malwareFamily.trim()
        if (raw && !INVALID_NAMES.has(raw.toLowerCase())) {
          families.add(raw)
        }
      }
    }
    return Array.from(families).sort((a, b) => a.localeCompare(b))
  }, [leads])

  const filtered = useMemo(() => {
    const subset = leads.filter((l) => {
      if (view === "for_review") {
        if (l.status !== "enriched") return false
      }
      else if (view === "approved") {
        if (l.status !== "approved") return false
      }
      else if (view === "discarded") {
        if (l.status !== "invalid" && l.status !== "discarded" && l.status !== "enrichment_failed") return false
      }
      else if (view === "rejected") {
        if (l.status !== "rejected" && l.status !== "junk") return false
      }
      else if (view === "pipeline") { return false }
      if (search) {
        const q = search.toLowerCase()
        if (!l.company.toLowerCase().includes(q) && !l.domain.toLowerCase().includes(q)) return false
      }
      if (scoreFilter === 'high') return l.score >= 80
      if (scoreFilter === 'med') return l.score >= 60 && l.score < 80
      if (scoreFilter === 'low') return l.score < 60
      if (signatureFilter !== 'all') {
        if (l.evidence.kind !== "malware" || l.evidence.malwareFamily !== signatureFilter) return false
      }
      return true
    })
    return [...subset].sort((a, b) => {
      let cmp: number
      if (sortKey === "score") cmp = a.score - b.score
      else if (sortKey === "dateFound") cmp = a.dateFound.localeCompare(b.dateFound)
      else cmp = String(a[sortKey]).localeCompare(String(b[sortKey]))
      return sortDir === "asc" ? cmp : -cmp
    })
  }, [leads, view, sortKey, sortDir, search, scoreFilter, signatureFilter])

  const filteredCandidates = useMemo(() => {
    const subset = rawCandidates.filter((cand) => {
      if (search) {
        const q = search.toLowerCase()
        const domainMatch = cand.domain.toLowerCase().includes(q)
        const companyMatch = (cand.company_name ?? "").toLowerCase().includes(q)
        const sourceMatch = cand.source.toLowerCase().includes(q)
        if (!domainMatch && !companyMatch && !sourceMatch) return false
      }
      if (pipelineStatusFilter !== "all") {
        if (cand.status !== pipelineStatusFilter) return false
      }
      return true
    })

    return [...subset].sort((a, b) => {
      let cmp = 0
      if (pipelineSortKey === "domain") {
        const nameA = a.company_name || a.domain
        const nameB = b.company_name || b.domain
        cmp = nameA.localeCompare(nameB)
      } else if (pipelineSortKey === "source") {
        cmp = a.source.localeCompare(b.source)
      } else if (pipelineSortKey === "status") {
        cmp = a.status.localeCompare(b.status)
      } else if (pipelineSortKey === "date") {
        const dateA = a.last_seen_at || a.created_at
        const dateB = b.last_seen_at || b.created_at
        cmp = dateA.localeCompare(dateB)
      }
      return pipelineSortDir === "asc" ? cmp : -cmp
    })
  }, [rawCandidates, search, pipelineStatusFilter, pipelineSortKey, pipelineSortDir])

  useEffect(() => {
    onFilteredChange?.(filtered)
  }, [filtered, onFilteredChange])

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortKey(key)
      setSortDir(key === "score" || key === "dateFound" ? "desc" : "asc")
    }
  }

  function togglePipelineSort(key: PipelineSortKey) {
    if (key === pipelineSortKey) {
      setPipelineSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setPipelineSortKey(key)
      setPipelineSortDir(key === "date" ? "desc" : "asc")
    }
  }

  const forReviewCount = leads.filter((l) => l.status === "enriched").length
  const approvedCount = leads.filter((l) => l.status === "approved").length
  const discardedCount = leads.filter((l) => l.status === "invalid" || l.status === "discarded" || l.status === "enrichment_failed").length
  const rejectedCount = leads.filter((l) => l.status === "rejected" || l.status === "junk").length
  const pipelineCount = rawCandidates.length

  const allSelected = filtered.length > 0 && selectedIds.size === filtered.length
  const someSelected = selectedIds.size > 0 && selectedIds.size < filtered.length

  function toggleSelectAll() {
    if (allSelected) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(filtered.map(l => l.id)))
    }
  }

  function toggleRowSelect(id: string) {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedIds(next)
  }

  async function handleBulkAction(action: "approved" | "rejected" | "junk" | "rerun_evaluation" | "rerun_enrichment") {
    if (!onBulkAction || selectedIds.size === 0) return
    setIsBulkActing(true)
    try {
      await onBulkAction(Array.from(selectedIds), action)
      setSelectedIds(new Set())
    } finally {
      setIsBulkActing(false)
    }
  }

  return (
    <section aria-label="Leads" className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between gap-4 border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold text-card-foreground">Leads</h2>
        <div className="flex items-center gap-1 rounded-md bg-muted p-0.5" role="tablist" aria-label="Lead view filter">
          <button
            role="tab"
            aria-selected={view === "for_review"}
            onClick={() => { setView("for_review"); setSelectedIds(new Set()) }}
            className={cn(
              "rounded px-2.5 py-1 text-xs transition-colors",
              view === "for_review"
                ? "bg-card font-medium text-card-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t("leads_table.tabs.for_review", { defaultValue: "For review" })} <span className="font-mono">({forReviewCount})</span>
          </button>
          <button
            role="tab"
            aria-selected={view === "approved"}
            onClick={() => { setView("approved"); setSelectedIds(new Set()) }}
            className={cn(
              "rounded px-2.5 py-1 text-xs transition-colors",
              view === "approved"
                ? "bg-card font-medium text-card-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t("leads_table.tabs.approved", { defaultValue: "Approved" })} <span className="font-mono">({approvedCount})</span>
          </button>
          <button
            role="tab"
            aria-selected={view === "discarded"}
            onClick={() => { setView("discarded"); setSelectedIds(new Set()) }}
            className={cn(
              "rounded px-2.5 py-1 text-xs transition-colors",
              view === "discarded"
                ? "bg-card font-medium text-card-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t("leads_table.tabs.discarded", { defaultValue: "Discarded" })} <span className="font-mono">({discardedCount})</span>
          </button>
          <button
            role="tab"
            aria-selected={view === "rejected"}
            onClick={() => { setView("rejected"); setSelectedIds(new Set()) }}
            className={cn(
              "rounded px-2.5 py-1 text-xs transition-colors",
              view === "rejected"
                ? "bg-card font-medium text-card-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t("leads_table.tabs.rejected", { defaultValue: "Rejected (junk)" })} <span className="font-mono">({rejectedCount})</span>
          </button>
          <button
            role="tab"
            aria-selected={view === "pipeline"}
            onClick={() => { setView("pipeline"); setSelectedIds(new Set()) }}
            className={cn(
              "rounded px-2.5 py-1 text-xs transition-colors",
              view === "pipeline"
                ? "bg-card font-medium text-card-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t("leads_table.tabs.pipeline", { defaultValue: "Pipeline" })} <span className="font-mono">({pipelineCount})</span>
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" aria-hidden="true" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("leads_table.search_placeholder", { defaultValue: "Search by company or domain…" })}
            className="w-full rounded-md border border-input bg-background py-1.5 pl-8 pr-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/50"
          />
        </div>
        {view !== "pipeline" ? (
          <>
            <div className="flex items-center gap-1" role="group" aria-label="Score filter">
              {(['all', 'high', 'med', 'low'] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setScoreFilter(f)}
                  className={cn(
                    "rounded px-2.5 py-1 text-xs transition-colors",
                    scoreFilter === f
                      ? "bg-card font-medium text-card-foreground shadow-sm ring-1 ring-border"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {f === 'all' ? 'All' : f === 'high' ? 'High 80+' : f === 'med' ? 'Med 60–79' : 'Low <60'}
                </button>
              ))}
            </div>

            {availableSignatures.length > 0 && (
              <select
                value={signatureFilter}
                onChange={(e) => setSignatureFilter(e.target.value)}
                className="rounded-md border border-input bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring/50"
                aria-label="Filter by malware signature"
              >
                <option value="all">All Signatures ({availableSignatures.length})</option>
                {availableSignatures.map((sig) => (
                  <option key={sig} value={sig}>
                    {sig}
                  </option>
                ))}
              </select>
            )}
          </>
        ) : (
          <select
            value={pipelineStatusFilter}
            onChange={(e) => setPipelineStatusFilter(e.target.value)}
            className="rounded-md border border-input bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring/50"
            aria-label="Filter candidates by status"
          >
            <option value="all">All Candidate Statuses ({rawCandidates.length})</option>
            <option value="new">New</option>
            <option value="evaluated">Evaluated</option>
            <option value="enriched">Enriched</option>
            <option value="invalid">Invalid</option>
          </select>
        )}
        
        {selectedIds.size > 0 && (
          <div className="flex items-center gap-2 border-l border-border pl-2 ml-1">
            <span className="text-xs font-medium text-muted-foreground">{selectedIds.size} {t("leads_table.selected", { defaultValue: "selected" })}</span>
            {view === "for_review" && (
              <>
                <button
                  onClick={() => handleBulkAction("approved")}
                  disabled={isBulkActing}
                  className="rounded px-2.5 py-1 text-xs font-medium bg-emerald-600/10 text-emerald-600 transition-colors hover:bg-emerald-600/20 disabled:opacity-50"
                >
                  {t("dashboard.stats.approved")}
                </button>
                <button
                  onClick={() => handleBulkAction("rejected")}
                  disabled={isBulkActing}
                  className="rounded px-2.5 py-1 text-xs font-medium bg-red-600/10 text-red-600 transition-colors hover:bg-red-600/20 disabled:opacity-50"
                >
                  {t("dashboard.stats.discarded")}
                </button>
                <button
                  onClick={() => handleBulkAction("junk")}
                  disabled={isBulkActing}
                  className="rounded px-2.5 py-1 text-xs font-medium bg-orange-600/10 text-orange-600 transition-colors hover:bg-orange-600/20 disabled:opacity-50"
                >
                  Mark as Junk
                </button>
              </>
            )}
            <button
              onClick={() => handleBulkAction("rerun_evaluation")}
              disabled={isBulkActing}
              className="rounded px-2.5 py-1 text-xs font-medium bg-slate-600/10 text-slate-700 dark:text-slate-300 transition-colors hover:bg-slate-600/20 disabled:opacity-50"
            >
              {t("leads_table.bulk.rerun_eval", { defaultValue: "Rerun Evaluation" })}
            </button>
            <button
              onClick={() => handleBulkAction("rerun_enrichment")}
              disabled={isBulkActing}
              className="rounded px-2.5 py-1 text-xs font-medium bg-slate-600/10 text-slate-700 dark:text-slate-300 transition-colors hover:bg-slate-600/20 disabled:opacity-50"
            >
              {t("leads_table.bulk.rerun_enrich", { defaultValue: "Rerun Enrichment" })}
            </button>
          </div>
        )}
      </div>

      {view !== "pipeline" && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th scope="col" className="w-10 px-4 py-2 text-left">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    ref={input => {
                      if (input) input.indeterminate = someSelected
                    }}
                    onChange={toggleSelectAll}
                    className="size-3.5 rounded border-input bg-background text-primary"
                  />
                </th>
                {columns.map((col) => (
                  <th key={col.key} scope="col" className={cn("px-4 py-2 text-left", col.className)}>
                    <button
                      onClick={() => toggleSort(col.key)}
                      className="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {col.label}
                      {sortKey === col.key ? (
                        sortDir === "asc" ? (
                          <ArrowUp className="size-3" aria-hidden="true" />
                        ) : (
                          <ArrowDown className="size-3" aria-hidden="true" />
                        )
                      ) : (
                        <ArrowUpDown className="size-3 opacity-40" aria-hidden="true" />
                      )}
                    </button>
                  </th>
                ))}
                <th scope="col" className="w-16 px-2 py-2 text-center" title={t("leads_table.columns.completeness", { defaultValue: "Status" })}>
                  <span className="text-xs font-medium text-muted-foreground">
                    {t("leads_table.columns.completeness", { defaultValue: "Status" })}
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={columns.length + 2} className="px-4 py-12">
                    <div className="flex flex-col items-center gap-2 text-center">
                      <div className="flex size-10 items-center justify-center rounded-full bg-muted">
                        <Inbox className="size-5 text-muted-foreground" aria-hidden="true" />
                      </div>
                      <p className="text-sm font-medium text-card-foreground">{emptyStates[view as "for_review"|"approved"|"discarded"|"rejected"].heading}</p>
                      <p className="text-sm text-muted-foreground">{emptyStates[view as "for_review"|"approved"|"discarded"|"rejected"].sub}</p>
                    </div>
                  </td>
                </tr>
              )}
              {filtered.map((lead) => {
                const score = scoreColorClasses(lead.score)
                return (
                  <tr
                    key={lead.id}
                    onClick={() => onSelect(lead)}
                    className={cn(
                      "cursor-pointer border-b border-border/60 transition-colors last:border-0 hover:bg-accent/50",
                      selectedId === lead.id && "bg-accent/70",
                      selectedIds.has(lead.id) && "bg-accent/30",
                      (lead.processing_generation && lead.processing_generation > 0) && "opacity-50"
                    )}
                  >
                    <td className="w-10 px-4 py-3" onClick={e => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(lead.id)}
                        onChange={() => toggleRowSelect(lead.id)}
                        className="size-3.5 rounded border-input bg-background text-primary"
                      />
                    </td>
                    <td className="px-4 py-3 font-medium text-card-foreground">
                      <div className="flex items-center gap-2">
                        <img
                          src={`https://www.google.com/s2/favicons?domain=${lead.domain}&sz=32`}
                          alt=""
                          className="size-5 rounded bg-white shadow-sm"
                          loading="lazy"
                        />
                        {lead.company}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <a
                        href={`https://${lead.domain}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 font-mono text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                      >
                        {lead.domain}
                        <ExternalLink className="size-3" aria-hidden="true" />
                      </a>
                      {lead.screenshot_url && (
                        <img
                          src={lead.screenshot_url}
                          alt=""
                          loading="lazy"
                          className="w-[1px] h-[1px] opacity-0 inline-block"
                          aria-hidden="true"
                          decoding="async"
                        />
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className={cn("w-7 text-right font-mono text-xs font-semibold", score.text)}>
                          {lead.score}
                        </span>
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                          <div className={cn("h-full rounded-full", score.bar)} style={{ width: `${lead.score}%` }} />
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        title={lead.status === "enrichment_failed" && lead.enrichment_attempt_count ? `Failed after ${lead.enrichment_attempt_count} attempts` : undefined}
                        className={cn(
                          "inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium",
                          statusBadgeClasses[lead.status],
                        )}
                      >
                        {t(`status.${lead.status}`, { defaultValue: statusLabels[lead.status] })}
                        {(lead.processing_generation && lead.processing_generation > 0) ? ` (Gen ${lead.processing_generation})` : ""}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-muted-foreground">
                      {formatDate(lead.dateFound)}
                    </td>
                    <td className="px-2 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                      {(() => {
                        const missing = getLeadMissingFields(lead)
                        const complete = missing.length === 0
                        return (
                          <span
                            title={complete ? "Complete" : `Missing: ${missing.join(", ")}`}
                            className={cn(
                              "inline-block size-1.5 rounded-full cursor-help",
                              complete ? "bg-emerald-500" : "bg-red-500"
                            )}
                          />
                        )
                      })()}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pipeline tab: raw candidates pre-evaluation */}
      {view === "pipeline" && (
        <div className="overflow-x-auto">
          {filteredCandidates.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-12 text-center">
              <div className="flex size-10 items-center justify-center rounded-full bg-muted">
                <Inbox className="size-5 text-muted-foreground" aria-hidden="true" />
              </div>
              <p className="text-sm font-medium text-card-foreground">{t("leads_table.empty.pipeline.heading", { defaultValue: "No candidates in pipeline" })}</p>
              <p className="text-sm text-muted-foreground">{t("leads_table.empty.pipeline.sub", { defaultValue: "Candidates discovered by Stage 2 will appear here before evaluation." })}</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th scope="col" className="px-4 py-2 text-left">
                    <button
                      onClick={() => togglePipelineSort("domain")}
                      className="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                    >
                      Domain
                      {pipelineSortKey === "domain" ? (
                        pipelineSortDir === "asc" ? (
                          <ArrowUp className="size-3" aria-hidden="true" />
                        ) : (
                          <ArrowDown className="size-3" aria-hidden="true" />
                        )
                      ) : (
                        <ArrowUpDown className="size-3 opacity-40" aria-hidden="true" />
                      )}
                    </button>
                  </th>
                  <th scope="col" className="px-4 py-2 text-left">
                    <button
                      onClick={() => togglePipelineSort("source")}
                      className="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {t("pipeline.source", { defaultValue: "Source" })}
                      {pipelineSortKey === "source" ? (
                        pipelineSortDir === "asc" ? (
                          <ArrowUp className="size-3" aria-hidden="true" />
                        ) : (
                          <ArrowDown className="size-3" aria-hidden="true" />
                        )
                      ) : (
                        <ArrowUpDown className="size-3 opacity-40" aria-hidden="true" />
                      )}
                    </button>
                  </th>
                  <th scope="col" className="px-4 py-2 text-left">
                    <button
                      onClick={() => togglePipelineSort("status")}
                      className="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {t("leads_table.columns.status", { defaultValue: "Status" })}
                      {pipelineSortKey === "status" ? (
                        pipelineSortDir === "asc" ? (
                          <ArrowUp className="size-3" aria-hidden="true" />
                        ) : (
                          <ArrowDown className="size-3" aria-hidden="true" />
                        )
                      ) : (
                        <ArrowUpDown className="size-3 opacity-40" aria-hidden="true" />
                      )}
                    </button>
                  </th>
                  <th scope="col" className="px-4 py-2 text-left">
                    <button
                      onClick={() => togglePipelineSort("date")}
                      className="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {t("leads_table.columns.date_modified", { defaultValue: "Date modified" })}
                      {pipelineSortKey === "date" ? (
                        pipelineSortDir === "asc" ? (
                          <ArrowUp className="size-3" aria-hidden="true" />
                        ) : (
                          <ArrowDown className="size-3" aria-hidden="true" />
                        )
                      ) : (
                        <ArrowUpDown className="size-3 opacity-40" aria-hidden="true" />
                      )}
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredCandidates.map((cand) => {
                  const statusColorMap: Record<string, string> = {
                    new: "bg-blue-500/10 text-blue-500",
                    evaluating: "bg-yellow-500/10 text-yellow-600",
                    evaluated: "bg-emerald-500/10 text-emerald-600",
                    pending_review: "bg-purple-500/10 text-purple-500",
                    approved: "bg-emerald-500/10 text-emerald-600",
                    rejected: "bg-red-500/10 text-red-500",
                    junk: "bg-zinc-500/10 text-zinc-500",
                    discarded: "bg-zinc-500/10 text-zinc-500",
                    duplicate: "bg-zinc-500/10 text-zinc-500",
                    enrichment_failed: "bg-orange-500/10 text-orange-500",
                  }
                  return (
                    <tr key={cand.id} className="border-b border-border/60 last:border-0 hover:bg-accent/50 transition-colors">
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-2">
                          <img
                            src={`https://www.google.com/s2/favicons?domain=${cand.domain}&sz=32`}
                            alt="" className="size-4 rounded bg-white" loading="lazy"
                          />
                          <a
                            href={`https://${cand.domain}`}
                            target="_blank" rel="noopener noreferrer"
                            className="font-mono text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline font-medium text-foreground"
                          >
                            {cand.company_name || cand.domain}
                          </a>
                        </div>
                      </td>
                      <td className="px-4 py-2 font-mono text-xs text-muted-foreground">{cand.source}</td>
                      <td className="px-4 py-2">
                        <span className={cn("inline-block rounded-full px-2 py-0.5 text-xs font-medium", statusColorMap[cand.status] ?? "bg-muted text-muted-foreground")}>
                          {t(`pipeline.status.${cand.status}`, { defaultValue: cand.status })}
                          {cand.enrichment_attempt_count > 0 && ` (${cand.enrichment_attempt_count})`}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-muted-foreground">
                        {formatDate(new Date(cand.last_seen_at || cand.created_at).toLocaleDateString("en-CA"))}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  )
}
