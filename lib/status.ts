import type { LeadStatus } from "@/lib/leads-data"

export const statusLabels: Record<LeadStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  enrichment_failed: "Enrich failed",
  junk: "Junk",
}

export const statusBadgeClasses: Record<LeadStatus, string> = {
  pending: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20",
  approved: "bg-green-500/10 text-green-500 border-green-500/20",
  rejected: "bg-red-500/10 text-red-500 border-red-500/20",
  enrichment_failed: "bg-orange-500/10 text-orange-500 border-orange-500/20",
  junk: "bg-zinc-500/10 text-zinc-500 border-zinc-500/20",
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

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "Unknown"
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
