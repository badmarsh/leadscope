"use client"

import { useCallback, useState } from "react"
import type { CampaignId } from "@/lib/leads-data"
import { CAMPAIGN_TO_DB_ID } from "@/lib/campaigns"

export interface UsageData {
  total_cost_usd: number
  by_stage: Record<string, number>
  by_provider: Record<string, number>
}

export function useUsage(onUnauthorized: () => void) {
  const [usage, setUsage] = useState<UsageData | null>(null)
  const DB_IDS = CAMPAIGN_TO_DB_ID

  const fetchUsage = useCallback(
    async (campaignId: CampaignId) => {
      try {
        const dbId = DB_IDS[campaignId]
        const r = await fetch(`/api/usage?campaign_id=${dbId}`)
        if (r.status === 401) {
          onUnauthorized()
          return
        }
        if (r.ok) {
          const data = await r.json()
          setUsage(data)
        }
      } catch {
        // silently degrade
      }
    },
    [DB_IDS, onUnauthorized],
  )

  return { usage, fetchUsage }
}
