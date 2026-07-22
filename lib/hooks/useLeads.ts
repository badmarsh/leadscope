"use client"

import { useCallback, useState } from "react"
import type { CampaignId, Lead } from "@/lib/leads-data"
import { CAMPAIGN_TO_DB_ID } from "@/lib/campaigns"
import { rowToLead } from "@/lib/leads-data"

export interface UseLeadsReturn {
  leads: Lead[]
  filteredLeads: Lead[]
  totalLeads: number
  loading: boolean
  page: number
  nextCursor: number | null
  setPage: React.Dispatch<React.SetStateAction<number>>
  setFilteredLeads: React.Dispatch<React.SetStateAction<Lead[]>>
  fetchLeads: (campaignId: CampaignId, currentPage?: number) => Promise<void>
  handleDecision: (id: string, status: "approved" | "rejected", note: string) => Promise<void>
  handleReopen: (id: string) => Promise<void>
  handleBulkAction: (ids: string[], action: "approved" | "rejected" | "rerun_evaluation" | "rerun_enrichment") => Promise<void>
  handleDraftGenerated: (id: string, draft: string) => void
}

export function useLeads(onUnauthorized: () => void, activeCampaign: CampaignId): UseLeadsReturn {
  const [leads, setLeads] = useState<Lead[]>([])
  const [filteredLeads, setFilteredLeads] = useState<Lead[]>([])
  const [totalLeads, setTotalLeads] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [nextCursor, setNextCursor] = useState<number | null>(null)

  const DB_IDS = CAMPAIGN_TO_DB_ID

  const fetchLeads = useCallback(
    async (campaignId: CampaignId, currentPage = 1) => {
      setLoading(true)
      try {
        const dbId = DB_IDS[campaignId]
        const r = await fetch(`/api/leads?campaign_id=${dbId}&page=${currentPage}&limit=50`)
        if (r.status === 401) {
          onUnauthorized()
          return
        }
        const data = await r.json()
        const mapped = (data.leads as Record<string, unknown>[]).map(rowToLead)
        setLeads(mapped)
        setNextCursor(data.nextCursor ?? null)
        setTotalLeads(data.total ?? 0)
      } catch {
        // silently degrade — keep current leads
      } finally {
        setLoading(false)
      }
    },
    [DB_IDS, onUnauthorized],
  )

  const handleDecision = async (id: string, status: "approved" | "rejected", note: string) => {
    setLeads((prev) => prev.map((l) => (l.id === id ? { ...l, status, note } : l)))
    try {
      const r = await fetch("/api/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_id: parseInt(id, 10), decision: status, note }),
      })
      if (!r.ok) {
        await fetchLeads(activeCampaign, page)
      }
    } catch {
      await fetchLeads(activeCampaign, page)
    }
  }

  const handleReopen = async (id: string) => {
    setLeads((prev) => prev.map((l) => (l.id === id ? { ...l, status: "pending" } : l)))
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

  const handleBulkAction = async (
    ids: string[],
    action: "approved" | "rejected" | "rerun_evaluation" | "rerun_enrichment",
  ) => {
    if (action === "approved" || action === "rejected") {
      setLeads((prev) =>
        prev.map((l) => (ids.includes(l.id) ? { ...l, status: action } : l)),
      )
    }

    try {
      const r = await fetch("/api/action/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_ids: ids.map((id) => parseInt(id, 10)), decision: action }),
      })
      if (!r.ok || action === "rerun_evaluation" || action === "rerun_enrichment") {
        await fetchLeads(activeCampaign, page)
      }
    } catch {
      await fetchLeads(activeCampaign, page)
    }
  }

  const handleDraftGenerated = (id: string, draft: string) => {
    setLeads((prev) => prev.map((l) => (l.id === id ? { ...l, draft_email: draft } : l)))
  }

  return {
    leads,
    filteredLeads,
    totalLeads,
    loading,
    page,
    nextCursor,
    setPage,
    setFilteredLeads,
    fetchLeads,
    handleDecision,
    handleReopen,
    handleBulkAction,
    handleDraftGenerated,
  }
}
