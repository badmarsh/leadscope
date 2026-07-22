"use client"

import { Activity } from "lucide-react"
import type { CampaignUsage, Lead } from "@/lib/leads-data"
import { cn } from "@/lib/utils"

interface StatsRowProps {
  leads: Lead[]
  usage: CampaignUsage
}

const stats = [
  { key: "pending", label: "Pending review", dot: "bg-amber-500" },
  { key: "approved", label: "Approved", dot: "bg-emerald-500" },
  { key: "rejected", label: "Rejected", dot: "bg-red-500" },
  { key: "enrichment_failed", label: "Enrich failed", dot: "bg-muted-foreground/50" },
] as const

export function StatsRow({ leads, usage }: StatsRowProps) {
  const counts = {
    pending: leads.filter((l) => l.status === "pending").length,
    approved: leads.filter((l) => l.status === "approved").length,
    rejected: leads.filter((l) => l.status === "rejected").length,
    enrichment_failed: leads.filter((l) => l.status === "enrichment_failed").length,
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
            {counts[s.key]}
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
