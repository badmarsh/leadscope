"use client"

import React from "react"
import { AlertTriangle, CheckCircle2 } from "lucide-react"

export interface PipelineCampaign {
  id: string
  name: string
  family: string
  added: string
  stale_after_days: number
  source_url: string
  publicwww_query: string | null
  fit: string | null
  location: string
  urlscan_pivot: string[]
  virustotal_pivot: {
    hashes: string[]
    domains: string[]
  }
  notes: string | null
  days_old: number
  is_stale: boolean
  is_template: boolean
}

interface CampaignCardProps {
  campaign: PipelineCampaign
  isSelected: boolean
  onSelect: (id: string) => void
}

export function CampaignCard({ campaign: c, isSelected, onSelect }: CampaignCardProps) {
  return (
    <div
      onClick={() => onSelect(c.id)}
      className={`group relative flex flex-col justify-between rounded-xl border p-4 transition-all cursor-pointer ${
        isSelected
          ? "border-primary bg-primary/5 shadow-md shadow-primary/5 ring-1 ring-primary"
          : "border-border bg-card hover:border-muted-foreground/30 hover:bg-accent/40"
      }`}
    >
      <div className="space-y-2">
        <div className="flex items-start justify-between gap-2">
          <span className="font-mono text-xs font-bold text-foreground">{c.id}</span>
          {c.is_template ? (
            <span className="inline-flex items-center gap-1 rounded bg-amber-500/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-amber-700 dark:text-amber-400 border border-amber-500/20">
              <AlertTriangle className="size-3" /> TEMPLATE
            </span>
          ) : c.is_stale ? (
            <span className="inline-flex items-center gap-1 rounded bg-red-500/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-red-600 dark:text-red-400 border border-red-500/20">
              <AlertTriangle className="size-3" /> STALE
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded bg-emerald-500/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
              <CheckCircle2 className="size-3" /> FRESH
            </span>
          )}
        </div>

        <h3 className="text-xs font-semibold line-clamp-2 text-foreground group-hover:text-primary">
          {c.name}
        </h3>
        <p className="text-[11px] text-muted-foreground">
          Family: <span className="font-medium text-foreground">{c.family}</span>
        </p>
      </div>

      <div className="mt-4 space-y-1.5 border-t border-border/60 pt-3 text-[10px] text-muted-foreground">
        <div className="flex justify-between">
          <span>Age: {c.days_old} days</span>
          <span>Stale: &gt;{c.stale_after_days}d</span>
        </div>
        <div className="flex justify-between items-center">
          <span>
            Location: <code className="text-foreground">{c.location}</code>
          </span>
          {c.fit && <span className="text-amber-500 font-mono text-[9px] truncate max-w-[110px]">{c.fit}</span>}
        </div>
      </div>
    </div>
  )
}
