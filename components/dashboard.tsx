"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { campaigns, type CampaignId, type Lead } from "@/lib/leads-data"
import { DB_ID_TO_CAMPAIGN, CAMPAIGN_TO_DB_ID } from "@/lib/campaigns"  // M3: shared map
import { useLeads } from "@/lib/hooks/useLeads"
import { useUsage } from "@/lib/hooks/useUsage"
import { LoginScreen } from "@/components/login-screen"
import { TopNav } from "@/components/top-nav"
import { PipelineStatus } from "@/components/pipeline-status"
import { StatsRow } from "@/components/stats-row"
import { LeadsTable } from "@/components/leads-table"
import { LeadDrawer } from "@/components/lead-drawer"
import { SettingsModal } from "@/components/settings-modal"
import { KnowledgeBaseModal } from "@/components/knowledge-base-modal"
import { HelpModal } from "@/components/help-modal"
import { DoNotContactModal } from "@/components/do-not-contact-modal"
import { N8nModal } from "@/components/n8n-modal"
import { LogViewer } from "@/components/LogViewer"
import { useTranslation } from "@/lib/i18n"
import { Crosshair, ShieldAlert, Rss } from "lucide-react"

const DARK_MODE_KEY = "leadscope-dark-mode"

// Map DB row → Lead shape expected by existing components
function rowToLead(row: Record<string, unknown>): Lead {
  const evidenceData = (row.evidence_data as Record<string, unknown> | null) ?? {}
  const evaluatorType = (evidenceData.evaluator_type as string | undefined) ?? "urls"

  let evidence: Lead["evidence"]

  if (evaluatorType === "image_quality" || evidenceData.product_images || evidenceData.scraped_product_images || evidenceData.images_analyzed) {
    const rawImages = [
      ...((evidenceData.product_images as string[] | undefined) ?? []),
      ...((evidenceData.scraped_product_images as string[] | undefined) ?? []),
      ...((evidenceData.images_analyzed as string[] | undefined) ?? []),
    ]
    const directImages = Array.from(new Set(rawImages.filter((src) => typeof src === "string" && (src.startsWith("http://") || src.startsWith("https://")))))

    evidence = {
      kind: "photos",
      photos: directImages.slice(0, 8).map((src, i) => ({
        src,
        label: `Product Image ${i + 1}`,
      })),
    }
  } else if (
    evaluatorType === "threat_intel" ||
    evidenceData.malware_family
  ) {
    evidence = {
      kind: "malware",
      malwareFamily: (evidenceData.malware_family as string) ?? "Unknown",
      sourcePost: {
        title: (evidenceData.source_post_title as string) ?? "Security intelligence source",
        url: (evidenceData.source_post_url as string) ?? "#",
      },
      lastConfirmed: (evidenceData.last_confirmed as string) ?? (row.created_at as string) ?? null,
    }
  } else {
    evidence = {
      kind: "urls",
      urls: (row.evidence_urls as string[] | undefined) ?? [],
    }
  }

  // Map DB status to Lead status — keep in sync with lib/leads-data.ts statusMap
  const statusMap: Record<string, Lead["status"]> = {
    pending_review: "pending",
    evaluating: "pending",           // actively being scored — show as pending
    new: "pending",                  // discovered, not yet evaluated
    evaluated: "evaluated",          // scored by LLM — ready for human review!
    enriched: "enriched",            // fully enriched — ready for human review!
    approved: "approved",
    rejected: "rejected",
    discarded: "discarded",          // auto-rejected by scorer
    junk: "junk",                    // manually marked junk by operator
    stale: "rejected",
    enrichment_failed: "enrichment_failed",
    invalid: "enrichment_failed",
    duplicate: "rejected",
  }

  return {
    id: String(row.id),
    campaignId: activeCampaignIdForRow(row.campaign_id as number),
    company: (row.company_name as string) ?? (row.domain as string),
    domain: row.domain as string,
    score: (row.score as number) ?? 0,
    status: statusMap[row.status as string] ?? "pending", // safe fallback for unknown DB statuses
    dateFound: new Date(row.created_at as string).toLocaleDateString("en-CA"),
    rationale: (row.rationale as string) ?? "",
    evidence,
    evidence_data: evidenceData,
    note: (row.note as string) ?? undefined,
    contact_email: (row.contact_email as string) ?? undefined,
    contact_phone: (row.contact_phone as string) ?? undefined,
    contact_name: (row.contact_name as string) ?? undefined,
    screenshot_url: (row.screenshot_url as string) ?? undefined,
    products_sold: (row.products_sold as string[]) ?? undefined,
    enrichment_report: (row.enrichment_report as string) ?? undefined,
    draft_email: (row.draft_email as string) ?? undefined,
    estimated_size: (row.estimated_size as string) ?? undefined,
    estimated_revenue: (row.estimated_revenue as string) ?? undefined,
    estimated_traffic: (row.estimated_traffic as string) ?? undefined,
    // Phase X fields
    audit_token: (row.audit_token as string) ?? undefined,
    mainwp_webhook_token: (row.mainwp_webhook_token as string) ?? undefined,
    proof_data: (evidenceData.proof_data as import("@/lib/leads-data").PhaseXProof) ?? undefined,
    exposure_scan: (evidenceData.exposure_scan as import("@/lib/leads-data").PhaseXExposure) ?? undefined,
  }
}

function activeCampaignIdForRow(dbCampaignId: number): CampaignId {
  return DB_ID_TO_CAMPAIGN[dbCampaignId] ?? "wp-remediation"  // M3: use shared map
}

const DB_CAMPAIGN_IDS: Record<CampaignId, number> = CAMPAIGN_TO_DB_ID  // M3: use shared map

export function Dashboard() {
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null) // null = loading
  const [activeCampaign, setActiveCampaign] = useState<CampaignId>("wp-remediation")
  const [leads, setLeads] = useState<Lead[]>([])
  const [filteredLeads, setFilteredLeads] = useState<Lead[]>([])
  const [tableState, setTableState] = useState({ view: "for_review", count: 0 })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [darkMode, setDarkMode] = useState(false)
  const [loading, setLoading] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [kbOpen, setKbOpen] = useState(false)
  const [dncOpen, setDncOpen] = useState(false)
  const [isHelpOpen, setIsHelpOpen] = useState(false)
  const [isN8nOpen, setIsN8nOpen] = useState(false)
  const [page, setPage] = useState(1)
  const [totalLeads, setTotalLeads] = useState(0)
  const [totalCandidates, setTotalCandidates] = useState(0)
  const [rawCandidates, setRawCandidates] = useState<Array<{id:number;domain:string;company_name:string|null;source:string;status:string;created_at:string;last_seen_at?:string;enrichment_attempt_count:number}>>([]) 
  const limit = 1000
  const [usage, setUsage] = useState<{
    openRouterSpend: string
    publicWwwUsed: number
    publicWwwLimit: number
  }>({ openRouterSpend: "$0.00", publicWwwUsed: 0, publicWwwLimit: 1000 })

  const { t } = useTranslation()

  const currentLeadIndex = filteredLeads.findIndex(l => l.id === selectedId)
  const hasNext = currentLeadIndex >= 0 && currentLeadIndex < filteredLeads.length - 1
  const hasPrev = currentLeadIndex > 0

  const handleNavigate = useCallback((dir: "next" | "prev") => {
    if (dir === "next" && hasNext) setSelectedId(filteredLeads[currentLeadIndex + 1].id)
    if (dir === "prev" && hasPrev) setSelectedId(filteredLeads[currentLeadIndex - 1].id)
  }, [hasNext, hasPrev, filteredLeads, currentLeadIndex])

  // Persist dark mode
  useEffect(() => {
    const stored = localStorage.getItem(DARK_MODE_KEY)
    if (stored !== null) setDarkMode(stored === "true")
  }, [])

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("dark", darkMode)
    root.classList.toggle("light", !darkMode)
  }, [darkMode])

  // Check session on mount
  useEffect(() => {
    fetch("/api/session")
      .then((r) => r.json())
      .then((d) => setLoggedIn(d.loggedIn === true))
      .catch(() => setLoggedIn(false))
  }, [])

  // Fetch leads when campaign or page changes (supports silent background AJAX updates)
  const fetchLeads = useCallback(async (campaignId: CampaignId, currentPage: number = 1, silent: boolean = false) => {
    if (!silent) setLoading(true)
    try {
      const dbId = DB_CAMPAIGN_IDS[campaignId]
      const r = await fetch(`/api/leads?campaign_id=${dbId}&page=${currentPage}&limit=${limit}`)
      if (r.status === 401) { setLoggedIn(false); return }
      const data = await r.json()
      setLeads((data.leads as Record<string, unknown>[]).map(rowToLead))
      setTotalLeads(data.total ?? 0)
    } catch {
      // silently degrade — keep current leads
    } finally {
      if (!silent) setLoading(false)
    }
  }, [limit])

  // Fetch raw pipeline candidates
  const fetchCandidates = useCallback(async (campaignId: CampaignId) => {
    try {
      const dbId = DB_CAMPAIGN_IDS[campaignId]
      const r = await fetch(`/api/candidates?campaign_id=${dbId}&limit=1000`)
      if (!r.ok) return
      const data = await r.json()
      setRawCandidates(data.candidates ?? [])
      setTotalCandidates(data.total ?? (data.candidates ?? []).length)
    } catch {
      // silently degrade
    }
  }, [])

  // Fetch usage for the header
  const fetchUsage = useCallback(async (campaignId: CampaignId) => {
    try {
      const dbId = DB_CAMPAIGN_IDS[campaignId]
      const r = await fetch(`/api/usage?campaign_id=${dbId}`)
      if (!r.ok) return
      const data = await r.json()
      const orRow = (data.spend as { provider: string; total_cost: number }[])?.find(
        (s) => s.provider === "openrouter",
      )
      const pwRow = (data.spend as { provider: string; total_queries: number }[])?.find(
        (s) => s.provider === "publicwww",
      )
      const pwBudget = (data.budgets as { provider: string; monthly_query_limit: number }[])?.find(
        (b) => b.provider === "publicwww",
      )
      setUsage({
        openRouterSpend: `$${Number(orRow?.total_cost ?? 0).toFixed(2)}`,
        publicWwwUsed: Number(pwRow?.total_queries ?? 0),
        publicWwwLimit: Number(pwBudget?.monthly_query_limit ?? 1000),
      })
    } catch {
      // silently degrade
    }
  }, [])

  useEffect(() => {
    if (loggedIn) {
      // Initial fetch with loading state
      fetchLeads(activeCampaign, page, false)
      fetchUsage(activeCampaign)
      fetchCandidates(activeCampaign)

      // Silent AJAX background updates every 10s (no UI flicker/loading skeleton)
      const interval = setInterval(() => {
        fetchLeads(activeCampaign, page, true)
        fetchUsage(activeCampaign)
        fetchCandidates(activeCampaign)
      }, 10000)

      return () => clearInterval(interval)
    }
  }, [loggedIn, activeCampaign, page, fetchLeads, fetchUsage, fetchCandidates])

  function toggleDarkMode() {
    setDarkMode((d) => {
      localStorage.setItem(DARK_MODE_KEY, String(!d))
      return !d
    })
  }

  async function handleLogin() {
    setLoggedIn(true)
    await new Promise((r) => setTimeout(r, 100))
    await fetchLeads(activeCampaign, page)
    await fetchUsage(activeCampaign)
  }

  async function handleLogout() {
    await fetch("/api/logout", { method: "POST" })
    setLoggedIn(false)
    setLeads([])
  }

  async function handleDecision(id: string, status: "approved" | "rejected", note: string) {
    // Optimistic update
    setLeads((prev) =>
      prev.map((l) => (l.id === id ? { ...l, status, note: note || undefined } : l)),
    )
    setSelectedId(null)

    // Persist to DB
    try {
      const r = await fetch("/api/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_id: parseInt(id, 10), decision: status, note }),
      })
      if (!r.ok) {
        // Revert optimistic update on failure
        await fetchLeads(activeCampaign, page, true)
      }
    } catch {
      await fetchLeads(activeCampaign, page, true)
    }
  }

  async function handleReopen(id: string) {
    // Optimistic update: reopen and clear stale note
    setLeads((prev) => prev.map((l) => (l.id === id ? { ...l, status: "pending" as const, note: undefined } : l)))
    setSelectedId(null)

    try {
      const r = await fetch("/api/action", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_id: parseInt(id, 10) }),
      })
      if (!r.ok) {
        await fetchLeads(activeCampaign, page, true)
      }
    } catch {
      await fetchLeads(activeCampaign, page, true)
    }
  }

  async function handleBulkAction(ids: string[], action: "approved" | "rejected" | "junk" | "rerun_evaluation" | "rerun_enrichment") {
    // Optimistic update for approved / rejected / junk
    if (action === "approved" || action === "rejected" || action === "junk") {
      setLeads((prev) =>
        prev.map((l) => (ids.includes(l.id) ? { ...l, status: action } : l)),
      )
    }
    setSelectedId(null)

    try {
      const r = await fetch("/api/action/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_ids: ids.map(id => parseInt(id, 10)), decision: action }),
      })
      if (!r.ok || action === "rerun_evaluation" || action === "rerun_enrichment") {
        await fetchLeads(activeCampaign, page, true)
      }
    } catch {
      await fetchLeads(activeCampaign, page, true)
    }
  }

  function handleDraftGenerated(id: string, draft: string) {
    setLeads((prev) => prev.map((l) => (l.id === id ? { ...l, draft_email: draft } : l)))
  }

  // Loading state
  if (loggedIn === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="text-sm text-muted-foreground">Loading…</div>
      </div>
    )
  }

  if (!loggedIn) {
    return <LoginScreen onLogin={handleLogin} />
  }

  const campaign = campaigns.find((c) => c.id === activeCampaign)!
  const campaignLeads = leads.filter((l) => l.campaignId === activeCampaign)
  const selectedLead = leads.find((l) => l.id === selectedId) ?? null

  return (
    <div className="min-h-screen bg-background">
      <TopNav
        activeCampaign={activeCampaign}
        onCampaignChange={(id) => {
          setActiveCampaign(id)
          setSelectedId(null)
          setPage(1)
        }}
        darkMode={darkMode}
        onToggleDarkMode={toggleDarkMode}
        onLogout={handleLogout}
        onSettingsOpen={() => setSettingsOpen(true)}
        onKbOpen={() => setKbOpen(true)}
        onDncOpen={() => setDncOpen(true)}
        onHelpOpen={() => setIsHelpOpen(true)}
        onN8nOpen={() => setIsN8nOpen(true)}
      />

      <main className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-6 lg:px-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-foreground">{campaign.name}</h1>
            <p className="text-sm text-muted-foreground">
              Review discovered leads and approve or reject them for outreach.
            </p>
          </div>
          {/* WP-only pipeline shortcut icons */}
          {activeCampaign === "wp-remediation" && (
            <div className="flex items-center gap-2 rounded-md border border-border bg-card p-1">
              <a
                href="/wp-hunter"
                title="WP Compromise Hunter Pipeline"
                className="flex size-8 items-center justify-center rounded-md text-cyan-600 dark:text-cyan-400 transition-colors hover:bg-cyan-500/15"
              >
                <Crosshair className="size-4" />
              </a>
              <a
                href="/seo-spam-hunter"
                title="SEO Spam & Backdoor Hunter Pipeline"
                className="flex size-8 items-center justify-center rounded-md text-amber-600 dark:text-amber-400 transition-colors hover:bg-amber-500/15"
              >
                <ShieldAlert className="size-4" />
              </a>
              <a
                href="/threat-feeds"
                title="Threat Intel Feeds"
                className="relative flex size-8 items-center justify-center rounded-md text-violet-600 dark:text-violet-400 transition-colors hover:bg-violet-500/15"
              >
                <Rss className="size-4" />
                <span className="absolute top-1.5 right-1.5 size-1.5 rounded-full bg-violet-500" />
              </a>
            </div>
          )}
        </div>

        <PipelineStatus campaignId={DB_CAMPAIGN_IDS[activeCampaign]} />

        <StatsRow leads={campaignLeads} usage={usage} rawCandidates={rawCandidates} totalCandidates={totalCandidates} />

        {loading ? (
          <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
            {t("dashboard.loading", { defaultValue: "Loading leads..." })}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <LeadsTable
              leads={campaignLeads}
              selectedId={selectedId}
              onSelect={(lead) => setSelectedId(lead.id)}
              onFilteredChange={(leads, view, candCount) => {
                setFilteredLeads(leads)
                setTableState({ view, count: view === "pipeline" ? candCount : leads.length })
              }}
              onBulkAction={handleBulkAction}
              activeCampaign={activeCampaign}
              rawCandidates={rawCandidates}
              totalCandidates={totalCandidates}
            />
            <div className="flex items-center justify-between px-2 text-sm text-muted-foreground">
              <div>
                {tableState.count === 0
                  ? (tableState.view === "pipeline" ? t("leads_table.empty.pipeline.heading", { defaultValue: "No candidates found" }) : t("leads_table.no_leads"))
                  : `Showing ${tableState.count} ${tableState.view === "pipeline" ? "candidates" : "leads"}`
                }
              </div>
              <div className="flex gap-2">
                <button
                  disabled={page === 1}
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  className="rounded-md border bg-card px-3 py-1 hover:bg-accent disabled:opacity-50"
                >
                  {t("dashboard.previous")}
                </button>
                <button
                  disabled={page * limit >= totalLeads}
                  onClick={() => setPage(p => p + 1)}
                  className="rounded-md border bg-card px-3 py-1 hover:bg-accent disabled:opacity-50"
                >
                  {t("dashboard.next")}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>

      <LeadDrawer
        lead={selectedLead}
        onClose={() => setSelectedId(null)}
        onDecision={handleDecision}
        onReopen={handleReopen}
        onNavigate={handleNavigate}
        hasNext={hasNext}
        hasPrev={hasPrev}
        onDraftGenerated={handleDraftGenerated}
        onBulkAction={(action) => handleBulkAction([selectedLead!.id], action)}
      />

      <SettingsModal
        open={settingsOpen}
        campaignDbId={DB_CAMPAIGN_IDS[activeCampaign]}
        onClose={() => setSettingsOpen(false)}
      />

      <KnowledgeBaseModal
        open={kbOpen}
        campaignDbId={DB_CAMPAIGN_IDS[activeCampaign]}
        onClose={() => setKbOpen(false)}
      />

      <DoNotContactModal
        open={dncOpen}
        campaignDbId={DB_CAMPAIGN_IDS[activeCampaign]}
        onClose={() => setDncOpen(false)}
      />

      <HelpModal
        isOpen={isHelpOpen}
        onClose={() => setIsHelpOpen(false)}
      />

      <N8nModal
        isOpen={isN8nOpen}
        onClose={() => setIsN8nOpen(false)}
      />

      <LogViewer />
    </div>
  )
}
