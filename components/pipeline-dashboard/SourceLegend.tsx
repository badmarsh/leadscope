"use client"

import React from "react"
import { cn } from "@/lib/utils"

export type ThreatSource = "urlhaus" | "threatfox" | "virustotal" | "virustotal_graph" | "urlscan" | "publicwww" | "certstream"

interface SourceConfig {
  id: string
  label: string
  activeClass: string
  inactiveClass: string
}

const SOURCES: SourceConfig[] = [
  {
    id: "urlhaus",
    label: "URLhaus",
    activeClass: "bg-cyan-500/20 text-cyan-600 border-cyan-500/40 dark:text-cyan-400",
    inactiveClass: "bg-muted/50 text-muted-foreground border-border hover:bg-cyan-500/10 hover:text-cyan-500",
  },
  {
    id: "threatfox",
    label: "ThreatFox",
    activeClass: "bg-red-500/20 text-red-600 border-red-500/40 dark:text-red-400",
    inactiveClass: "bg-muted/50 text-muted-foreground border-border hover:bg-red-500/10 hover:text-red-500",
  },
  {
    id: "virustotal",
    label: "VirusTotal",
    activeClass: "bg-blue-500/20 text-blue-600 border-blue-500/40 dark:text-blue-400",
    inactiveClass: "bg-muted/50 text-muted-foreground border-border hover:bg-blue-500/10 hover:text-blue-500",
  },
  {
    id: "urlscan",
    label: "urlscan.io",
    activeClass: "bg-purple-500/20 text-purple-600 border-purple-500/40 dark:text-purple-400",
    inactiveClass: "bg-muted/50 text-muted-foreground border-border hover:bg-purple-500/10 hover:text-purple-500",
  },
  {
    id: "publicwww",
    label: "PublicWWW",
    activeClass: "bg-emerald-500/20 text-emerald-600 border-emerald-500/40 dark:text-emerald-400",
    inactiveClass: "bg-muted/50 text-muted-foreground border-border hover:bg-emerald-500/10 hover:text-emerald-500",
  },
  {
    id: "certstream",
    label: "CT Stream",
    activeClass: "bg-violet-500/20 text-violet-600 border-violet-500/40 dark:text-violet-400",
    inactiveClass: "bg-muted/50 text-muted-foreground border-border hover:bg-violet-500/10 hover:text-violet-500",
  },
]

interface SourceLegendProps {
  activeSource: string
  onSelectSource: (source: string) => void
  sourceCounts?: Record<string, number>
}

export function SourceLegend({ activeSource, onSelectSource, sourceCounts }: SourceLegendProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="font-medium text-muted-foreground mr-1">Sources:</span>
      <button
        onClick={() => onSelectSource("all")}
        className={cn(
          "px-2.5 py-1 rounded-md border text-xs font-semibold transition-all cursor-pointer",
          activeSource === "all"
            ? "bg-primary text-primary-foreground border-primary"
            : "bg-card text-muted-foreground border-border hover:bg-accent hover:text-foreground"
        )}
      >
        All {sourceCounts?.all !== undefined ? `(${sourceCounts.all})` : ""}
      </button>

      {SOURCES.map((s) => {
        const count = sourceCounts?.[s.id]
        const isSelected = activeSource === s.id
        return (
          <button
            key={s.id}
            onClick={() => onSelectSource(isSelected ? "all" : s.id)}
            className={cn(
              "px-2.5 py-1 rounded-md border text-xs font-medium transition-all cursor-pointer flex items-center gap-1",
              isSelected ? s.activeClass + " font-bold shadow-sm" : s.inactiveClass
            )}
          >
            <span>{s.label}</span>
            {count !== undefined && (
              <span className="font-mono text-[10px] opacity-80">({count})</span>
            )}
          </button>
        )
      })}
    </div>
  )
}
