import type { LeadStatus } from "@/lib/leads-data"

export const statusLabels: Record<LeadStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  enrichment_failed: "Enrich failed",
}

export const statusBadgeClasses: Record<LeadStatus, string> = {
  pending:
    "bg-amber-500/15 text-amber-700 dark:text-amber-400 border border-amber-500/30",
  approved:
    "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30",
  rejected: "bg-red-500/15 text-red-700 dark:text-red-400 border border-red-500/30",
  enrichment_failed:
    "bg-muted text-muted-foreground border border-border",
}

export function scoreColorClasses(score: number): { text: string; bar: string } {
  if (score >= 80) return { text: "text-emerald-700 dark:text-emerald-400", bar: "bg-emerald-500" }
  if (score >= 60) return { text: "text-amber-700 dark:text-amber-400", bar: "bg-amber-500" }
  if (score === 0) return { text: "text-muted-foreground", bar: "bg-muted-foreground/40" }
  if (score > 0) return { text: "text-red-700 dark:text-red-400", bar: "bg-red-500" }
  return { text: "text-muted-foreground", bar: "bg-muted-foreground/40" }
}

export function formatDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  })
}
