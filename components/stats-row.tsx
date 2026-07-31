"use client"

import { Activity } from "lucide-react"
import type { CampaignUsage, Lead } from "@/lib/leads-data"
import { cn } from "@/lib/utils"
import { useTranslation } from "@/lib/i18n"

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

interface StatsRowProps {
  leads: Lead[]
  usage: CampaignUsage
  rawCandidates?: RawCandidate[]
  totalCandidates?: number
}

export function StatsRow({ leads, usage, rawCandidates = [], totalCandidates }: StatsRowProps) {
  const { t } = useTranslation()

  const stats = [
    { key: "for_review", label: t("dashboard.stats.for_review", { defaultValue: "For review" }), dot: "bg-purple-500" },
    { key: "approved", label: t("dashboard.stats.approved", { defaultValue: "Approved" }), dot: "bg-emerald-500" },
    { key: "discarded", label: t("dashboard.stats.discarded", { defaultValue: "Discarded" }), dot: "bg-zinc-400" },
    { key: "pipeline", label: t("dashboard.stats.pipeline", { defaultValue: "Pipeline" }), dot: "bg-blue-500" },
  ] as const

  const counts = {
    for_review: leads.filter((l) => l.status === "enriched").length,
    approved: leads.filter((l) => l.status === "approved").length,
    discarded: leads.filter((l) => l.status === "invalid" || l.status === "discarded" || l.status === "enrichment_failed").length,
    pipeline: totalCandidates ?? rawCandidates.filter((cand) => cand.status !== "enriched" && cand.status !== "approved" && cand.status !== "rejected" && cand.status !== "junk" && cand.status !== "discarded" && cand.status !== "invalid").length,
  }

  const pct = Math.round((usage.publicWwwUsed / usage.publicWwwLimit) * 100)

  return (
    <section aria-label="Campaign stats" className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      {stats.map((s) => (
        <div key={s.key} className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center gap-2">
            <span className={cn("size-2 rounded-full", s.dot)} aria-hidden="true" />
            <span className="text-xs text-muted-foreground">{s.label}</span>
          </div>
          <p className="mt-2 font-mono text-2xl font-semibold text-card-foreground">
            {counts[s.key as keyof typeof counts]}
          </p>
        </div>
      ))}

      <div className="col-span-2 rounded-lg border border-border bg-card p-4 lg:col-span-1">
        <div className="flex items-center gap-2">
          <Activity className="size-3.5 text-muted-foreground" aria-hidden="true" />
          <span className="text-xs text-muted-foreground">Usage this month</span>
        </div>
        <p className="mt-2 font-mono text-sm text-card-foreground">
          {usage.openRouterSpend} OpenRouter
        </p>
        <div className="mt-1.5 flex items-center gap-2">
          <div
            role="progressbar"
            aria-valuenow={usage.publicWwwUsed}
            aria-valuemin={0}
            aria-valuemax={usage.publicWwwLimit}
            aria-label="PublicWWW query usage"
            className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted"
          >
            <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
          </div>
          <span className="whitespace-nowrap font-mono text-xs text-muted-foreground">
            {usage.publicWwwUsed}/{usage.publicWwwLimit} PublicWWW
          </span>
        </div>
      </div>
    </section>
  )
}
