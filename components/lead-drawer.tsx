"use client"

import { useEffect, useRef, useState } from "react"
import { Check, Copy, ExternalLink, ImageOff, RotateCcw, ShieldAlert, X, Users, Euro, Activity, ChevronLeft, ChevronRight, AlertTriangle, Link2 } from "lucide-react"
import Image from "next/image"
import type { Lead, PhaseXProof, PhaseXExposure } from "@/lib/leads-data"
import { formatTimestamp, scoreColorClasses, statusBadgeClasses, statusLabels } from "@/lib/status"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { useTranslation } from "@/lib/i18n"

interface LeadDrawerProps {
  lead: Lead | null
  onClose: () => void
  onDecision: (id: string, status: "approved" | "rejected", note: string) => void
  onReopen: (id: string) => void
  onNavigate?: (dir: "next" | "prev") => void
  hasNext?: boolean
  hasPrev?: boolean
  onDraftGenerated?: (id: string, draft: string) => void
  onBulkAction?: (action: "approved" | "rejected" | "junk" | "rerun_evaluation" | "rerun_enrichment") => void
}

export function LeadDrawer({ lead, onClose, onDecision, onReopen, onNavigate, hasNext, hasPrev, onDraftGenerated, onBulkAction }: LeadDrawerProps) {
  const [note, setNote] = useState("")
  const [copied, setCopied] = useState(false)
  const [copiedEmail, setCopiedEmail] = useState(false)
  const [copiedPhone, setCopiedPhone] = useState(false)
  const [copiedDraft, setCopiedDraft] = useState(false)
  const [copiedAudit, setCopiedAudit] = useState(false)
  const [isGeneratingDraft, setIsGeneratingDraft] = useState(false)
  const { t } = useTranslation()
  const noteRef = useRef("")
  noteRef.current = note

  useEffect(() => {
    setNote(lead?.note ?? "")
    setCopied(false)
    setCopiedEmail(false)
    setCopiedPhone(false)
  }, [lead])

  useEffect(() => {
    if (!lead) return
    const { id, status } = lead
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose()
        return
      }
      // Guard: don't fire decision shortcuts while typing in an input/textarea
      const target = e.target as HTMLElement
      if (target.tagName === "TEXTAREA" || target.tagName === "INPUT" || target.isContentEditable) return
      if (e.key === "ArrowRight" && hasNext && onNavigate) {
        e.preventDefault()
        onNavigate("next")
        return
      }
      if (e.key === "ArrowLeft" && hasPrev && onNavigate) {
        e.preventDefault()
        onNavigate("prev")
        return
      }
      if (status !== "pending") return
      if (e.key === "a" || e.key === "A") {
        e.preventDefault()
        onDecision(id, "approved", noteRef.current)
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault()
        onDecision(id, "rejected", noteRef.current)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [lead, onClose, onDecision, onNavigate, hasNext, hasPrev])

  if (!lead) return null

  const score = scoreColorClasses(lead.score)
  const isDecided = lead.status === "approved" || lead.status === "rejected" || lead.status === "enrichment_failed"

  function copyDomain() {
    if (!lead) return
    navigator.clipboard.writeText(lead.domain).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  function copyEmail() {
    if (!lead?.contact_email) return
    navigator.clipboard.writeText(lead.contact_email).then(() => {
      setCopiedEmail(true)
      setTimeout(() => setCopiedEmail(false), 1500)
    })
  }

  function copyPhone() {
    if (!lead?.contact_phone) return
    navigator.clipboard.writeText(lead.contact_phone).then(() => {
      setCopiedPhone(true)
      setTimeout(() => setCopiedPhone(false), 1500)
    })
  }

  function copyDraft() {
    if (!lead?.draft_email) return
    navigator.clipboard.writeText(lead.draft_email).then(() => {
      setCopiedDraft(true)
      setTimeout(() => setCopiedDraft(false), 1500)
    })
  }

  async function handleGenerateDraft() {
    if (!lead) return
    setIsGeneratingDraft(true)
    try {
      const res = await fetch("/api/leads/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ leadId: lead.id }),
      })
      if (!res.ok) throw new Error("Failed to generate draft")
      const data = await res.json()
      onDraftGenerated?.(lead.id, data.draftEmail)
    } catch (e) {
      console.error(e)
    } finally {
      setIsGeneratingDraft(false)
    }
  }

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/40"
        aria-hidden="true"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Lead details for ${lead.company}`}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-background shadow-xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-foreground">{lead.company}</h2>
            <div className="mt-0.5 flex items-center gap-1">
              <a
                href={`https://${lead.domain}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-mono text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              >
                {lead.domain}
                <ExternalLink className="size-3" aria-hidden="true" />
              </a>
              <button
                onClick={copyDomain}
                aria-label={copied ? "Domain copied" : "Copy domain to clipboard"}
                className="flex size-5 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                {copied ? (
                  <Check className="size-3 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
                ) : (
                  <Copy className="size-3" aria-hidden="true" />
                )}
              </button>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span
              className={cn("font-mono text-sm font-semibold", score.text)}
              aria-label={`Opportunity score: ${lead.score}`}
            >
              {lead.score}
            </span>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-xs font-medium",
                statusBadgeClasses[lead.status],
              )}
            >
              {statusLabels[lead.status]}
            </span>
            {onNavigate && (
              <div className="ml-2 flex items-center gap-0.5 rounded-md border border-border bg-card p-0.5">
                <button
                  onClick={() => onNavigate("prev")}
                  disabled={!hasPrev}
                  title="Previous lead (Left Arrow)"
                  className="flex size-6 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-30"
                >
                  <ChevronLeft className="size-4" />
                </button>
                <button
                  onClick={() => onNavigate("next")}
                  disabled={!hasNext}
                  title="Next lead (Right Arrow)"
                  className="flex size-6 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-30"
                >
                  <ChevronRight className="size-4" />
                </button>
              </div>
            )}
            <button
              onClick={onClose}
              aria-label="Close details"
              className="ml-1 flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          <section aria-label="Rationale">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {t("lead_drawer.rationale", { defaultValue: "Rationale" })}
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-foreground">{lead.rationale}</p>
          </section>

          {(lead.enrichment_report || lead.contact_email || lead.contact_phone || (lead.products_sold && lead.products_sold.length > 0) || lead.screenshot_url || lead.domain || lead.estimated_size || lead.estimated_revenue || lead.estimated_traffic) && (
            <section aria-label="Company Overview" className="mt-6 border-t border-border pt-6">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {t("lead_drawer.company_overview", { defaultValue: "Company Overview" })}
              </h3>

              {(lead.estimated_size || lead.estimated_revenue || lead.estimated_traffic) && (
                <div className="mt-3 grid grid-cols-3 gap-2">
                  <div className="flex flex-col items-center justify-center rounded-md border border-border bg-card p-3 text-center">
                    <Users className="mb-1.5 size-4 text-muted-foreground" aria-hidden="true" />
                    <span className="text-xs font-medium text-foreground">{lead.estimated_size || "Unknown"}</span>
                    <span className="mt-0.5 text-[10px] uppercase text-muted-foreground">{t("lead_drawer.employees", { defaultValue: "Employees" })}</span>
                  </div>
                  <div className="flex flex-col items-center justify-center rounded-md border border-border bg-card p-3 text-center">
                    <Euro className="mb-1.5 size-4 text-muted-foreground" aria-hidden="true" />
                    <span className="text-xs font-medium text-foreground">{lead.estimated_revenue || "Unknown"}</span>
                    <span className="mt-0.5 text-[10px] uppercase text-muted-foreground">{t("lead_drawer.revenue", { defaultValue: "Revenue" })}</span>
                  </div>
                  <div className="flex flex-col items-center justify-center rounded-md border border-border bg-card p-3 text-center">
                    <Activity className="mb-1.5 size-4 text-muted-foreground" aria-hidden="true" />
                    <span className="text-xs font-medium text-foreground">{lead.estimated_traffic || "Unknown"}</span>
                    <span className="mt-0.5 text-[10px] uppercase text-muted-foreground">{t("lead_drawer.web_traffic", { defaultValue: "Web Traffic" })}</span>
                  </div>
                </div>
              )}

              {(lead.screenshot_url || lead.domain) && (
                <figure className="mt-3 overflow-hidden rounded-md border border-border bg-muted">
                  <div className="relative w-full" style={{ aspectRatio: "16/10" }}>
                    <Image
                      src={lead.screenshot_url || `https://api.microlink.io/?url=${encodeURIComponent(`https://${lead.domain}`)}&screenshot=true&meta=false&embed=screenshot.url`}
                      alt={`Screenshot of ${lead.company}'s website`}
                      fill
                      className="object-cover object-top"
                      unoptimized
                      onError={(e) => {
                        // Hide broken image, show placeholder
                        const img = e.currentTarget as HTMLImageElement
                        img.style.display = "none"
                        const parent = img.parentElement
                        if (parent && !parent.querySelector(".ss-fallback")) {
                          const fb = document.createElement("div")
                          fb.className = "ss-fallback flex items-center justify-center h-full text-muted-foreground text-xs gap-2"
                          fb.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 9h6M9 13h4"/></svg>Screenshot unavailable`
                          parent.appendChild(fb)
                        }
                      }}
                    />
                  </div>
                  <figcaption className="flex items-center gap-1.5 bg-muted px-2 py-1.5 font-mono text-xs text-muted-foreground">
                    <span className="size-1.5 rounded-full bg-emerald-500 inline-block" />
                    <a
                      href={`https://${lead.domain}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:underline underline-offset-2 hover:text-foreground"
                    >
                      {lead.domain}
                    </a>
                    {" — "}{t("lead_drawer.homepage", { defaultValue: "Homepage" })}
                  </figcaption>
                </figure>
              )}

              {lead.enrichment_report && (
                <div className="mt-4 rounded-md bg-accent/50 p-3 text-sm leading-relaxed text-foreground">
                  {lead.enrichment_report}
                </div>
              )}

              <div className="mt-4 flex flex-col gap-2">
                {lead.contact_name && (
                  <div className="flex items-center justify-between border-b border-border pb-2 text-sm">
                    <span className="text-muted-foreground">{t("lead_drawer.contact_name", { defaultValue: "Name" })}:</span>
                    <span className="font-medium text-foreground">{lead.contact_name}</span>
                  </div>
                )}
                {lead.contact_email && (
                  <div className="flex items-center justify-between border-b border-border pb-2 text-sm">
                    <span className="text-muted-foreground">{t("lead_drawer.email", { defaultValue: "Email" })}:</span>
                    <div className="flex items-center gap-1">
                      <a
                        href={`mailto:${lead.contact_email}`}
                        className="font-medium text-foreground underline-offset-2 hover:underline"
                      >
                        {lead.contact_email}
                      </a>
                      <button
                        onClick={copyEmail}
                        aria-label={copiedEmail ? "Email copied" : "Copy email to clipboard"}
                        className="flex size-5 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                      >
                        {copiedEmail ? (
                          <Check className="size-3 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
                        ) : (
                          <Copy className="size-3" aria-hidden="true" />
                        )}
                      </button>
                    </div>
                  </div>
                )}
                {lead.contact_phone && (
                  <div className="flex items-center justify-between border-b border-border pb-2 text-sm">
                    <span className="text-muted-foreground">{t("lead_drawer.phone", { defaultValue: "Phone" })}:</span>
                    <div className="flex items-center gap-1">
                      <a
                        href={`tel:${lead.contact_phone}`}
                        className="font-medium text-foreground underline-offset-2 hover:underline"
                      >
                        {lead.contact_phone}
                      </a>
                      <button
                        onClick={copyPhone}
                        aria-label={copiedPhone ? "Phone copied" : "Copy phone to clipboard"}
                        className="flex size-5 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                      >
                        {copiedPhone ? (
                          <Check className="size-3 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
                        ) : (
                          <Copy className="size-3" aria-hidden="true" />
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {lead.products_sold && lead.products_sold.length > 0 && (
                <div className="mt-4">
                  <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("lead_drawer.products_services", { defaultValue: "Products / Services" })}</span>
                  <ul className="mt-2 flex flex-col gap-1 text-sm text-foreground">
                    {lead.products_sold.map((product, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" />
                        <span>{product}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}

          <section aria-label="Evidence" className="mt-6 border-t border-border pt-6">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {t("lead_drawer.evidence", { defaultValue: "Evidence" })}
            </h3>

            {lead.evidence.kind === "urls" && (
              <ul className="mt-2 flex flex-col gap-1.5">
                {lead.evidence.urls.map((url) => (
                  <li key={url}>
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1.5 font-mono text-xs text-card-foreground transition-colors hover:bg-accent"
                    >
                      <ExternalLink className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
                      <span className="truncate">{url}</span>
                    </a>
                  </li>
                ))}
              </ul>
            )}

            {lead.evidence.kind === "photos" &&
              (lead.evidence.photos.length > 0 ? (
                <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {lead.evidence.photos.map((photo, idx) => (
                    <figure key={`${photo.src}-${idx}`} className="group flex flex-col overflow-hidden rounded-md border border-border bg-card transition-all hover:border-primary/50">
                      <div className="relative aspect-square w-full overflow-hidden bg-muted">
                        <Image
                          src={photo.src || "/placeholder.svg"}
                          alt={`Product photo: ${photo.label}`}
                          fill
                          sizes="(max-width: 640px) 50vw, 25vw"
                          className="object-cover transition-transform duration-200 group-hover:scale-105"
                        />
                      </div>
                      <figcaption className="truncate px-2.5 py-1.5 font-mono text-[11px] font-medium text-muted-foreground border-t border-border">
                        {photo.label}
                      </figcaption>
                    </figure>
                  ))}
                </div>
              ) : (
                <div className="mt-2 flex items-center gap-2 rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                  <ImageOff className="size-4" aria-hidden="true" />
                  {t("lead_drawer.no_photos", { defaultValue: "No product images could be scraped for this lead." })}
                </div>
              ))}

            {lead.evidence.kind === "malware" && (
              <div className="mt-2 flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-red-500/30 bg-red-500/15 px-2.5 py-1 font-mono text-xs font-semibold text-red-700 dark:text-red-400">
                    <ShieldAlert className="size-3.5" aria-hidden="true" />
                    {lead.evidence.malwareFamily}
                  </span>
                </div>
                <a
                  href={lead.evidence.sourcePost.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-start gap-1.5 rounded-md border border-border bg-card px-2.5 py-2 text-xs text-card-foreground transition-colors hover:bg-accent"
                >
                  <ExternalLink className="mt-0.5 size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <span className="text-pretty">{lead.evidence.sourcePost.title}</span>
                </a>
                <p className="font-mono text-xs text-muted-foreground">
                  Last confirmed present: {formatTimestamp(lead.evidence.lastConfirmed)} UTC
                </p>
              </div>
            )}
          </section>

          {/* Campaign-conditional right panel: PDF brochure (Jenex), Product List (shoe-photo), Threat Intel (wp-remediation) */}
          {(() => {
            const ed = lead.evidence_data as Record<string, unknown> | undefined
            const campaignId = lead.campaignId

            if (campaignId === "jenex") {
              // Jenex: show PDF Brochure / Catalogue section
              const pdfUrl = (ed?.pdf_brochure_url ?? ed?.catalogue_url ?? ed?.brochure_url) as string | undefined
              return (
                <section aria-label="PDF Brochure" className="mt-6 border-t border-border pt-6">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                    {t("lead_drawer.pdf_brochure", { defaultValue: "PDF Brochure / Catalogue" })}
                  </h3>
                  {pdfUrl ? (
                    <a
                      href={pdfUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm text-card-foreground transition-colors hover:bg-accent"
                    >
                      <ExternalLink className="size-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate font-mono text-xs">{pdfUrl}</span>
                    </a>
                  ) : (
                    <p className="text-sm text-muted-foreground">{t("lead_drawer.no_brochure", { defaultValue: "No brochure URL found" })}</p>
                  )}
                </section>
              )
            }

            if (campaignId === "shoe-photo") {
              // Shoe-photo: show Product List section
              const productsUrl = (ed?.products_url ?? ed?.product_list_url) as string | undefined
              const productCount = (ed?.product_count ?? ed?.total_products) as number | undefined
              const categories = (ed?.product_categories ?? ed?.categories) as string[] | undefined
              const hasProductData = productsUrl || productCount !== undefined || (categories && categories.length > 0)
              return (
                <section aria-label="Product List" className="mt-6 border-t border-border pt-6">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                    {t("lead_drawer.product_list", { defaultValue: "Product List" })}
                  </h3>
                  {hasProductData ? (
                    <div className="flex flex-col gap-2">
                      {productsUrl && (
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-muted-foreground">{t("lead_drawer.products_url", { defaultValue: "Products URL" })}:</span>
                          <a
                            href={productsUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 font-mono text-xs text-primary underline-offset-2 hover:underline"
                          >
                            {productsUrl}
                            <ExternalLink className="size-3" />
                          </a>
                        </div>
                      )}
                      {productCount !== undefined && (
                        <div className="flex items-center justify-between border-t border-border pt-2 text-sm">
                          <span className="text-muted-foreground">{t("lead_drawer.product_count", { defaultValue: "Products" })}:</span>
                          <span className="font-medium text-foreground">{productCount}</span>
                        </div>
                      )}
                      {categories && categories.length > 0 && (
                        <div className="border-t border-border pt-2">
                          <span className="text-xs text-muted-foreground">{t("lead_drawer.product_categories", { defaultValue: "Categories" })}:</span>
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {categories.map((cat, i) => (
                              <span key={i} className="rounded-full bg-accent px-2 py-0.5 text-xs text-accent-foreground">{cat}</span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">{t("lead_drawer.no_product_data", { defaultValue: "No product data found" })}</p>
                  )}
                </section>
              )
            }

            // WP-remediation (and any other campaign): Threat Intelligence panel
            const proof = (lead.proof_data ?? ed?.proof_data ?? null) as PhaseXProof | null
            const exposure = (lead.exposure_scan ?? ed?.exposure_scan ?? null) as PhaseXExposure | null
            const auditUrl = lead.audit_token ? `${typeof window !== "undefined" ? window.location.origin : ""}/audit/${lead.audit_token}` : null
            const firmographicScore = ed?.firmographic_score as number | undefined
            const wealthTld = ed?.wealth_index_tld as string | undefined
            const hasPhaseX = proof || exposure?.critical_found || auditUrl || firmographicScore !== undefined
            if (!hasPhaseX) return null
            return (
              <section aria-label="Phase X Intel" className="mt-6 border-t border-border pt-6">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                  {t("lead_drawer.threat_intel", { defaultValue: "Threat Intelligence" })}
                </h3>
                <div className="flex flex-col gap-3">
                  {firmographicScore !== undefined && (
                    <div className="rounded-md border border-blue-500/30 bg-blue-500/5 p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wide">
                          Firmographic Score
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Score: <span className="font-semibold text-foreground">+{firmographicScore}</span>
                        {wealthTld && ` (derived from .${wealthTld})`}
                      </p>
                    </div>
                  )}
                  {proof && (
                    <div className="rounded-md border border-red-500/30 bg-red-500/5 p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <ShieldAlert className="size-3.5 text-red-500" />
                        <span className="text-xs font-semibold text-red-600 dark:text-red-400 uppercase tracking-wide">
                          {proof.proof_type === "google_serp_spam" ? "SEO Spam Indexed" : "Cloaked Redirect"}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">{proof.evidence_text}</p>
                      {proof.proof_type === "google_serp_spam" && proof.example_url && (
                        <a href={proof.example_url} target="_blank" rel="noopener noreferrer"
                          className="mt-2 inline-flex items-center gap-1 text-xs text-blue-500 hover:underline">
                          <ExternalLink className="size-3" />
                          {proof.example_title || proof.example_url}
                        </a>
                      )}
                    </div>
                  )}
                  {exposure?.critical_found && (
                    <div className="rounded-md border border-orange-500/30 bg-orange-500/5 p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <AlertTriangle className="size-3.5 text-orange-500" />
                        <span className="text-xs font-semibold text-orange-600 dark:text-orange-400 uppercase tracking-wide">Critical Exposure</span>
                      </div>
                      <ul className="mt-1 flex flex-col gap-1">
                        {exposure.exposures.map((exp, i) => (
                          <li key={i} className="font-mono text-xs text-muted-foreground">{exp.url}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {auditUrl && (
                    <div className="rounded-md border border-border bg-card p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <Link2 className="size-3.5 text-muted-foreground" />
                        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Shadow Audit URL</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <code className="flex-1 truncate rounded bg-muted px-2 py-1 font-mono text-[10px] text-muted-foreground">
                          /audit/{lead.audit_token?.slice(0, 16)}…
                        </code>
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(auditUrl).then(() => {
                              setCopiedAudit(true)
                              setTimeout(() => setCopiedAudit(false), 1500)
                            })
                          }}
                          className="flex size-7 shrink-0 items-center justify-center rounded border border-border text-muted-foreground hover:bg-accent hover:text-foreground"
                          title="Copy audit URL"
                        >
                          {copiedAudit ? <Check className="size-3 text-emerald-600" /> : <Copy className="size-3" />}
                        </button>
                        <a href={auditUrl} target="_blank" rel="noopener noreferrer"
                          className="flex size-7 shrink-0 items-center justify-center rounded border border-border text-muted-foreground hover:bg-accent hover:text-foreground">
                          <ExternalLink className="size-3" />
                        </a>
                      </div>
                    </div>
                  )}
                </div>
              </section>
            )
          })()}

          {lead.status === "approved" && (
            <section aria-label="Draft Email" className="mt-6 border-t border-border pt-6">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {t("lead_drawer.draft_email", { defaultValue: "Draft Email" })}
              </h3>
              {lead.draft_email ? (
                <div className="group relative mt-3 rounded-md border border-border bg-card p-3">
                  <div className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                    {lead.draft_email}
                  </div>
                  <button
                    onClick={copyDraft}
                    title="Copy Draft Email"
                    className="absolute right-2 top-2 flex size-6 items-center justify-center rounded-md border border-border bg-background text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:bg-accent hover:text-foreground"
                  >
                    {copiedDraft ? <Check className="size-3 text-emerald-600 dark:text-emerald-400" /> : <Copy className="size-3" />}
                  </button>
                </div>
              ) : (
                <div className="mt-3">
                  <Button
                    onClick={handleGenerateDraft}
                    disabled={isGeneratingDraft}
                    variant="outline"
                    className="w-full text-xs"
                  >
                    {isGeneratingDraft ? "Generating..." : "Generate Draft"}
                  </Button>
                </div>
              )}
            </section>
          )}

          <section aria-label="Review note" className="mt-6">
            <label
              htmlFor="review-note"
              className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
            >
              Note (optional)
            </label>
            <textarea
              id="review-note"
              rows={3}
              placeholder="Add context for this decision..."
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="mt-2 w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/50"
            />
          </section>
        </div>

        <div className="border-t border-border px-5 py-4">
          <div className="flex items-center gap-2">
            {isDecided ? (
              <>
                <Button variant="outline" className="flex-1 bg-transparent" onClick={() => onReopen(lead.id)}>
                  <RotateCcw className="size-4" aria-hidden="true" />
                  Reopen
                </Button>
                {onBulkAction && (
                  <Button variant="outline" className="flex-1 bg-transparent" onClick={() => onBulkAction("rerun_evaluation")}>
                    <RotateCcw className="size-4" aria-hidden="true" />
                    Reset to New
                  </Button>
                )}
              </>
            ) : (
              <>
                <Button
                  className="flex-1 bg-emerald-600 text-white hover:bg-emerald-700"
                  onClick={() => onDecision(lead.id, "approved", note)}
                >
                  <Check className="size-4" aria-hidden="true" />
                  Approve
                  <kbd className="ml-1 rounded border border-white/30 bg-white/10 px-1.5 py-px font-mono text-[10px] font-medium leading-tight">
                    A
                  </kbd>
                </Button>
                <Button
                  variant="outline"
                  className="flex-1 border-red-500/40 text-red-700 hover:bg-red-500/10 dark:text-red-400"
                  onClick={() => onDecision(lead.id, "rejected", note)}
                >
                  <X className="size-4" aria-hidden="true" />
                  Reject
                  <kbd className="ml-1 rounded border border-red-500/30 bg-red-500/10 px-1.5 py-px font-mono text-[10px] font-medium leading-tight">
                    R
                  </kbd>
                </Button>
              </>
            )}
          </div>
          {!isDecided && (
            <p className="text-center text-[10px] text-muted-foreground mt-1">
              Keyboard: <kbd>A</kbd> approve · <kbd>R</kbd> reject · <kbd>Esc</kbd> close
            </p>
          )}
        </div>
      </aside>
    </>
  )
}
