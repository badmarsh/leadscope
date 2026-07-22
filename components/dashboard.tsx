"use client"

import { useCallback, useEffect, useState } from "react"
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
import { N8nModal } from "@/components/n8n-modal"
import { LogViewer } from "@/components/LogViewer"
import { useTranslation } from "@/lib/i18n"

const DARK_MODE_KEY = "leadscope-dark-mode"

// Map DB row → Lead shape expected by existing components
function rowToLead(row: Record<string, unknown>): Lead {
  const evidenceData = (row.evidence_data as Record<string, unknown> | null) ?? {}
  const evaluatorType = (evidenceData.evaluator_type as string | undefined) ?? "urls"

  let evidence: Lead["evidence"]

  if (evaluatorType === "image_quality" || evidenceData.images_analyzed) {
    const images = (evidenceData.images_analyzed as string[] | undefined) ?? []
    evidence = {
      kind: "photos",
      photos: images.slice(0, 4).map((src) => ({ src, label: "Product image" })),
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
      lastConfirmed: (evidenceData.last_confirmed as string) ?? null,
    }
  } else {
    evidence = {
      kind: "urls",
      urls: (row.evidence_urls as string[] | undefined) ?? [],
    }
  }

  // Map DB status to Lead status
  const statusMap: Record<string, Lead["status"]> = {
    pending_review: "pending",
    approved: "approved",
    rejected: "rejected",
    enrichment_failed: "enrichment_failed",
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
  }
}

function activeCampaignIdForRow(dbCampaignId: number): CampaignId {
  return DB_ID_TO_CAMPAIGN[dbCampaignId] ?? "jenex"  // M3: use shared map
}

const DB_CAMPAIGN_IDS: Record<CampaignId, number> = CAMPAIGN_TO_DB_ID  // M3: use shared map

export function Dashboard() {
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null) // null = loading
  const [activeCampaign, setActiveCampaign] = useState<CampaignId>("jenex")
  const [leads, setLeads] = useState<Lead[]>([])
  const [filteredLeads, setFilteredLeads] = useState<Lead[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [darkMode, setDarkMode] = useState(false)
  const [loading, setLoading] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [kbOpen, setKbOpen] = useState(false)
  const [isHelpOpen, setIsHelpOpen] = useState(false)
  const [isN8nOpen, setIsN8nOpen] = useState(false)
  const [page, setPage] = useState(1)
  const [totalLeads, setTotalLeads] = useState(0)
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

  // Fetch leads when campaign or page changes
  const fetchLeads = useCallback(async (campaignId: CampaignId, currentPage: number = 1) => {
    setLoading(true)
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
      setLoading(false)
    }
  }, [limit])

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
      fetchLeads(activeCampaign, page)
      fetchUsage(activeCampaign)
    }
  }, [loggedIn, activeCampaign, page, fetchLeads, fetchUsage])

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
        await fetchLeads(activeCampaign, page)
      }
    } catch {
      await fetchLeads(activeCampaign, page)
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
        await fetchLeads(activeCampaign, page)
      }
    } catch {
      await fetchLeads(activeCampaign, page)
    }
  }

  async function handleBulkAction(ids: string[], action: "approved" | "rejected" | "rerun_evaluation" | "rerun_enrichment") {
    // Optimistic update for approved / rejected
    if (action === "approved" || action === "rejected") {
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
        await fetchLeads(activeCampaign, page)
      }
    } catch {
      await fetchLeads(activeCampaign, page)
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
        onHelpOpen={() => setIsHelpOpen(true)}
        onN8nOpen={() => setIsN8nOpen(true)}
      />

      <main className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-6 lg:px-6">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-foreground">{campaign.name}</h1>
          <p className="text-sm text-muted-foreground">
            Review discovered leads and approve or reject them for outreach.
          </p>
        </div>

        <PipelineStatus campaignId={DB_CAMPAIGN_IDS[activeCampaign]} />

        <StatsRow leads={campaignLeads} usage={usage} />

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
              onFilteredChange={setFilteredLeads}
              onBulkAction={handleBulkAction}
            />
            <div className="flex items-center justify-between px-2 text-sm text-muted-foreground">
              <div>
                {totalLeads === 0
                  ? t("leads_table.no_leads")
                  : `Showing ${(page - 1) * limit + 1}–${Math.min(page * limit, totalLeads)} of ${totalLeads} leads`
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
