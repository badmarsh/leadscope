import { X, HelpCircle, Workflow, Network, Database, BrainCircuit, Bot } from "lucide-react"
import { useEffect } from "react"
import { useTranslation } from "@/lib/i18n"

interface HelpModalProps {
  isOpen: boolean
  onClose: () => void
}

export function HelpModal({ isOpen, onClose }: HelpModalProps) {
  const { t } = useTranslation()
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    if (isOpen) window.addEventListener("keydown", handleEscape)
    return () => window.removeEventListener("keydown", handleEscape)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="relative w-full max-w-4xl max-h-[85vh] overflow-hidden rounded-xl bg-card border border-border shadow-2xl flex flex-col"
        role="dialog"
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4 bg-muted/30">
          <div className="flex items-center gap-3">
            <div className="flex size-8 items-center justify-center rounded-md bg-primary/10 text-primary">
              <HelpCircle className="size-5" />
            </div>
            <h2 className="text-xl font-semibold">How Leadscope Works</h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="size-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-8">
          <section>
            <h3 className="text-lg font-medium flex items-center gap-2 mb-4">
              <Workflow className="size-5 text-blue-500" />
              The 5-Stage Pipeline
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
              {[
                { stage: 1, title: "ICP Definition", desc: "Define the Ideal Customer Profile and generate search queries." },
                { stage: 2, title: "Target Finding", desc: "Scrape search engines to find potential domains matching the queries." },
                { stage: 3, title: "Evaluation", desc: "Deeply scrape domains and use LLM to score them against the ICP." },
                { stage: 4, title: "Human Review", desc: "You review the scored candidates in this dashboard (Approve/Reject)." },
                { stage: 5, title: "Enrichment", desc: "Approved leads are enriched with contacts, tech stack, and CRM sync." },
              ].map((s) => (
                <div key={s.stage} className="bg-muted/50 p-4 rounded-lg border border-border/50">
                  <div className="text-xs font-bold text-muted-foreground uppercase mb-1">Stage {s.stage}</div>
                  <div className="font-semibold text-sm mb-2">{s.title}</div>
                  <div className="text-xs text-muted-foreground leading-relaxed">{s.desc}</div>
                </div>
              ))}
            </div>
          </section>

          <section>
            <h3 className="text-lg font-medium flex items-center gap-2 mb-4">
              <Network className="size-5 text-emerald-500" />
              Detailed Pipeline Logic
            </h3>
            <div className="space-y-6">
              
              <div className="bg-card border border-border rounded-lg p-5 space-y-3">
                <h4 className="font-semibold text-primary text-base border-b border-border pb-2">1. JENEX HU HVAC Pipeline</h4>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  This pipeline discovers and qualifies Hungarian HVAC installers and distributors.
                </p>
                <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1.5 ml-2">
                  <li><strong>Target Finding:</strong> Uses Python-based keyword search waterfall (Exa, Tavily, Serper, SerpAPI, Brave) with terms like <em>"légtechnika szerelés"</em>.</li>
                  <li><strong>Data Ingestion:</strong> Extracts domain from search results. If no domain exists, the lead is immediately <strong>dropped</strong>.</li>
                  <li><strong>Evaluation (Backend):</strong> 
                    <ul className="list-[circle] list-inside ml-6 mt-1 space-y-1">
                      <li>Scrapes up to 6 pages of the website using Crawl4AI.</li>
                      <li>Uses Vision AI to analyze product images (looking for spiral ducts, SWAH corner brackets).</li>
                      <li><strong>Disqualifiers:</strong> If the domain/company name contains "jenex", or if the company is not in Hungary, it scores 0.</li>
                      <li><strong>Auto-Discard:</strong> If the LLM score is below the configured threshold (e.g., 20) or if JENEX is detected, the lead is silently marked as <code>discarded</code> and hidden from the dashboard.</li>
                    </ul>
                  </li>
                  <li><strong>Enrichment:</strong> After human approval, it runs Crawl4AI to scrape the site, extracts deterministic metadata via <code>extruct</code>, normalizes phone numbers, and uses an LLM to fill data gaps (email, revenue/size estimates).</li>
                </ul>
              </div>

              <div className="bg-card border border-border rounded-lg p-5 space-y-3">
                <h4 className="font-semibold text-primary text-base border-b border-border pb-2">2. Shoe Boutique Photo Upgrade Pipeline</h4>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  This pipeline targets independent shoe boutiques with poor quality product photography.
                </p>
                <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1.5 ml-2">
                  <li><strong>Target Finding:</strong> Uses keyword search waterfall to find local shoe boutiques.</li>
                  <li><strong>Evaluation (Backend):</strong> 
                    <ul className="list-[circle] list-inside ml-6 mt-1 space-y-1">
                      <li>Scrapes website using Firecrawl to extract all product images.</li>
                      <li>Vision AI evaluates image quality (lighting, resolution, background).</li>
                      <li><strong>Disqualifiers:</strong> Large e-commerce brands (Nike, Adidas) or stock-photo sites are immediately disqualified.</li>
                      <li><strong>Exceptions:</strong> If no images are found, the lead scores 0 and is auto-discarded.</li>
                    </ul>
                  </li>
                  <li><strong>Enrichment:</strong> Scrapes site with Crawl4AI and generates firmographics along with a cold email hook.</li>
                </ul>
              </div>

              <div className="bg-card border border-border rounded-lg p-5 space-y-3">
                <h4 className="font-semibold text-primary text-base border-b border-border pb-2">3. WordPress Remediation Pipeline</h4>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  This pipeline targets businesses running outdated WordPress sites.
                </p>
                <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1.5 ml-2">
                  <li><strong>Target Finding:</strong> Uses a Python script to scan PublicWWW for domains matching specific malware code signatures. <em>Applies vertical filtering to exclude non-commercial/gov sites.</em></li>
                  <li><strong>Evaluation:</strong> Re-verifies malware on the live site using Crawl4AI, checks reputation via Google Safe Browsing/VirusTotal, uses Wayback Machine for recency (identifying recent cleanups as warm leads), and checks WP versions via RSS for CVE risks.</li>
                  <li><strong>Auto-Discard:</strong> Sites that do not have the signature in the fresh scrape or are conclusively clean score low and are discarded.</li>
                  <li><strong>Enrichment:</strong> Scrapes site with Crawl4AI and generates firmographics along with a cold email hook.</li>
                </ul>
              </div>

            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
