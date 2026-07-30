import type { Lead, LeadStatus } from "@/lib/leads-data"

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

/** Returns list of missing required field labels for a lead, empty = complete (green). */
export function getLeadMissingFields(lead: Lead): string[] {
  const missing: string[] = []
  const ed = (lead.evidence_data ?? {}) as Record<string, unknown>

  // Universal checks
  if (!lead.rationale) missing.push("Rationale")
  if (!lead.enrichment_report) missing.push("Company overview")
  if (!lead.screenshot_url) missing.push("Screenshot")
  if (!lead.contact_email) missing.push("Email")
  if (!lead.contact_phone) missing.push("Phone")
  if (!lead.products_sold || lead.products_sold.length === 0) missing.push("Products/Services")

  // Evidence check
  if (lead.campaignId === "jenex") {
    if (lead.evidence.kind !== "urls" || (lead.evidence as { kind: "urls"; urls: string[] }).urls.length === 0) {
      missing.push("Evidence URLs")
    }
    // PDF brochure is nice-to-have, not hard required for green
  } else if (lead.campaignId === "shoe-photo") {
    if (lead.evidence.kind !== "photos" || (lead.evidence as { kind: "photos"; photos: unknown[] }).photos.length === 0) {
      missing.push("Product images")
    }
  } else if (lead.campaignId === "wp-remediation") {
    if (lead.evidence.kind !== "malware") missing.push("Malware evidence")
  }

  return missing
}

export function isLeadComplete(lead: Lead): boolean {
  return getLeadMissingFields(lead).length === 0
}
