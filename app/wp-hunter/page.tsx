"use client"

import { useState, useEffect, useRef } from "react"
import Link from "next/link"
import {
  Crosshair,
  ShieldAlert,
  Search,
  Play,
  Upload,
  FileText,
  RefreshCw,
  ArrowLeft,
  Download,
  Layers,
  Sparkles,
  Rss,
  GitBranch,
} from "lucide-react"

import { CampaignCard, PipelineCampaign } from "@/components/pipeline-dashboard/CampaignCard"
import { CampaignDetailDrawer } from "@/components/pipeline-dashboard/CampaignDetailDrawer"
import { ExecutionTerminal } from "@/components/pipeline-dashboard/ExecutionTerminal"
import { FindingsTable, RawFinding } from "@/components/pipeline-dashboard/FindingsTable"
import { ReportViewer, ReportData } from "@/components/pipeline-dashboard/ReportViewer"

export default function WpHunterPage() {
  const [campaigns, setCampaigns] = useState<PipelineCampaign[]>([])
  const [selectedCampaignId, setSelectedCampaignId] = useState<string>("")
  const [pasteContent, setPasteContent] = useState<string>("")
  const [forceStale, setForceStale] = useState<boolean>(false)
  const [vtPivotDomains, setVtPivotDomains] = useState<boolean>(false)
  const [vtGraph, setVtGraph] = useState<boolean>(false)

  const [executing, setExecuting] = useState<boolean>(false)
  const [logs, setLogs] = useState<string>("")
  const [activeTab, setActiveTab] = useState<"findings" | "reports">("findings")

  const [findings, setFindings] = useState<RawFinding[]>([])
  const [reportList, setReportList] = useState<string[]>([])
  const [currentReport, setCurrentReport] = useState<ReportData | null>(null)
  const [loading, setLoading] = useState<boolean>(true)

  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    fetchCampaigns()
    fetchReports()
    fetchFindings()
  }, [])

  const fetchCampaigns = async () => {
    try {
      const res = await fetch("/api/wp-hunter/campaigns")
      const data = await res.json()
      if (data.campaigns) {
        setCampaigns(data.campaigns)
        if (data.campaigns.length > 0 && !selectedCampaignId) {
          const nonTemplate = data.campaigns.find((c: PipelineCampaign) => !c.is_template)
          setSelectedCampaignId(nonTemplate ? nonTemplate.id : data.campaigns[0].id)
        }
      }
    } catch (err) {
      console.error("Failed to fetch campaigns:", err)
    } finally {
      setLoading(false)
    }
  }

  const fetchFindings = async (cid?: string) => {
    try {
      const targetCid = cid || selectedCampaignId
      const url = targetCid
        ? `/api/wp-hunter/findings?campaignId=${encodeURIComponent(targetCid)}`
        : "/api/wp-hunter/findings"
      const res = await fetch(url)
      const data = await res.json()
      if (data.findings) {
        setFindings(data.findings)
      }
    } catch (err) {
      console.error("Failed to fetch findings:", err)
    }
  }

  const fetchReports = async (dir?: string) => {
    try {
      const url = dir
        ? `/api/wp-hunter/reports?dir=${encodeURIComponent(dir)}`
        : "/api/wp-hunter/reports"
      const res = await fetch(url)
      const data = await res.json()
      if (data.reports) {
        setReportList(data.reports)
      }
      if (data.currentReport) {
        setCurrentReport(data.currentReport)
      }
    } catch (err) {
      console.error("Failed to fetch reports:", err)
    }
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (event) => {
      if (event.target?.result) {
        setPasteContent(event.target.result as string)
      }
    }
    reader.readAsText(file)
  }

  const stopExecution = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setExecuting(false)
  }

  const handleRunPipeline = (stage: string) => {
    if (!selectedCampaignId) return
    stopExecution()

    setExecuting(true)
    setLogs(`[${new Date().toLocaleTimeString()}] Streaming stage '${stage}' for campaign '${selectedCampaignId}'...\n\n`)

    const params = new URLSearchParams({
      stage,
      campaignId: selectedCampaignId,
      vtGraph: String(vtGraph),
      vtPivotDomains: String(vtPivotDomains),
      forceStale: String(forceStale),
    })
    if ((stage === "ingest" || stage === "run") && pasteContent) {
      params.set("pasteContent", pasteContent)
    }

    const es = new EventSource(`/api/wp-hunter/run?${params.toString()}`)
    eventSourceRef.current = es

    es.onmessage = (e) => {
      if (e.data === "[DONE]") {
        stopExecution()
        setLogs((prev) => prev + "\n[Execution finished]")
        fetchFindings()
        fetchReports()
      } else {
        setLogs((prev) => prev + e.data + "\n")
      }
    }

    es.onerror = () => {
      stopExecution()
      setLogs((prev) => prev + "\n[Stream connection closed]")
    }
  }

  const handleSaveCampaign = async (campaignId: string, updatedFields: Partial<PipelineCampaign>) => {
    try {
      const res = await fetch(`/api/wp-hunter/campaigns/${encodeURIComponent(campaignId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updatedFields),
      })
      const data = await res.json()
      if (data.campaign) {
        setCampaigns((prev) =>
          prev.map((c) => (c.id === campaignId ? { ...c, ...data.campaign } : c))
        )
      }
    } catch (err) {
      console.error("Failed to update campaign:", err)
    }
  }

  const selectedCampaign = campaigns.find((c) => c.id === selectedCampaignId) || null

  return (
    <div className="min-h-screen bg-background text-foreground pb-12">
      {/* Top Header */}
      <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft className="size-4" />
              <span>Back to Dashboard</span>
            </Link>
            <div className="h-4 w-px bg-border" />
            <div className="flex items-center gap-2">
              <div className="flex size-7 items-center justify-center rounded-md bg-cyan-500/15 text-cyan-600 dark:text-cyan-400">
                <Crosshair className="size-4" />
              </div>
              <h1 className="text-base font-bold tracking-tight">WordPress Compromise Hunter Pipeline</h1>
              <span className="rounded-full bg-cyan-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-cyan-600 dark:text-cyan-400">
                v0.2.0
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href="/seo-spam-hunter"
              className="flex items-center gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-600 dark:text-amber-400 transition-colors hover:bg-amber-500/20"
            >
              <ShieldAlert className="size-3.5" />
              <span>Switch to SEO Spam Hunter</span>
            </Link>

            <button
              onClick={() => {
                fetchCampaigns()
                fetchReports()
                fetchFindings()
              }}
              title="Refresh Data"
              className="flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <RefreshCw className="size-3.5" />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        {/* Campaign Cards Section */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold tracking-tight text-foreground">
              <Layers className="size-4 text-cyan-500" />
              Target Campaigns ({campaigns.length})
            </h2>
            <span className="text-xs text-muted-foreground">
              Click a campaign card to select & edit inline
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {campaigns.map((c) => (
              <CampaignCard
                key={c.id}
                campaign={c}
                isSelected={c.id === selectedCampaignId}
                onSelect={setSelectedCampaignId}
              />
            ))}
          </div>

          {/* Campaign Inline Detail Drawer */}
          {selectedCampaign && (
            <CampaignDetailDrawer
              campaign={selectedCampaign}
              onSave={handleSaveCampaign}
            />
          )}
        </section>

        {/* Pipeline Control Panel */}
        <section className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-3">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-semibold tracking-tight text-foreground">
                <Sparkles className="size-4 text-cyan-500" />
                Pipeline Execution Control Panel
              </h2>
              <p className="text-xs text-muted-foreground">
                Execute passive malware recon, ingest threat feeds, and perform VirusTotal graph pivots.
              </p>
            </div>

            {selectedCampaign && (
              <div className="flex items-center gap-2 rounded-lg bg-muted/60 px-3 py-1.5 text-xs">
                <span className="text-muted-foreground">Active Campaign:</span>
                <span className="font-mono font-bold text-cyan-600 dark:text-cyan-400">{selectedCampaign.id}</span>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Left Column: Data Input & Options */}
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-foreground mb-1.5">
                  PublicWWW Export Data (CSV / Text Paste)
                </label>
                <textarea
                  value={pasteContent}
                  onChange={(e) => setPasteContent(e.target.value)}
                  placeholder="Paste lines (e.g. domain.com 1234)..."
                  className="w-full h-32 rounded-lg border border-input bg-background p-3 text-xs font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
                />
              </div>

              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 text-xs font-medium cursor-pointer text-muted-foreground hover:text-foreground">
                  <Upload className="size-3.5" />
                  <span>Upload CSV Export</span>
                  <input
                    type="file"
                    accept=".csv,.txt"
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                </label>
                {pasteContent && (
                  <span className="text-[11px] font-mono text-emerald-600 dark:text-emerald-400">
                    ✓ {pasteContent.split("\n").filter(Boolean).length} lines loaded
                  </span>
                )}
              </div>

              {/* Flags & Options */}
              <div className="rounded-lg border border-border/80 bg-muted/40 p-3 space-y-2 text-xs">
                <span className="font-semibold text-foreground">Pipeline Options</span>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={forceStale}
                    onChange={(e) => setForceStale(e.target.checked)}
                    className="rounded border-input text-cyan-600 focus:ring-cyan-500"
                  />
                  <span className="text-muted-foreground">
                    Bypass Freshness Gate (<code className="text-foreground">--i-know-this-is-stale</code>)
                  </span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={vtPivotDomains}
                    onChange={(e) => setVtPivotDomains(e.target.checked)}
                    className="rounded border-input text-cyan-600 focus:ring-cyan-500"
                  />
                  <span className="text-muted-foreground">
                    Pivot Contacted Domains on VirusTotal (<code className="text-foreground">--vt-pivot-domains</code>)
                  </span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={vtGraph}
                    onChange={(e) => setVtGraph(e.target.checked)}
                    className="rounded border-input text-cyan-600 focus:ring-cyan-500"
                  />
                  <span className="text-muted-foreground">
                    VirusTotal 2-Hop Graph Walk (<code className="text-foreground">--vt-graph</code>)
                  </span>
                </label>
              </div>
            </div>

            {/* Right Column: Active Specs & Action Buttons */}
            <div className="space-y-4 flex flex-col justify-between">
              {selectedCampaign ? (
                <div className="rounded-lg border border-border bg-background p-4 space-y-2 text-xs">
                  <div className="flex items-center justify-between border-b border-border pb-2">
                    <span className="font-semibold text-foreground">Query Specs</span>
                    <span className="font-mono text-muted-foreground">{selectedCampaign.family}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">PublicWWW Query: </span>
                    <code className="bg-muted px-1.5 py-0.5 rounded text-[11px] font-mono text-foreground break-all">
                      {selectedCampaign.publicwww_query || "(null - direct pivot)"}
                    </code>
                  </div>
                  <div>
                    <span className="text-muted-foreground">urlscan Pivot: </span>
                    <code className="bg-muted px-1.5 py-0.5 rounded text-[11px] font-mono text-foreground">
                      {selectedCampaign.urlscan_pivot.join(" OR ") || "None"}
                    </code>
                  </div>
                  <div>
                    <span className="text-muted-foreground">VirusTotal Hashes: </span>
                    <span className="font-mono text-foreground font-semibold">
                      {selectedCampaign.virustotal_pivot?.hashes?.length || 0} IOCs
                    </span>
                  </div>
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
                  Select a campaign above to view execution specifications.
                </div>
              )}

              {/* Action Buttons */}
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => handleRunPipeline("run")}
                  disabled={executing || !selectedCampaignId}
                  className="col-span-2 flex items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-xs font-semibold text-primary-foreground shadow transition-colors hover:bg-primary/90 disabled:opacity-50"
                >
                  {executing ? <RefreshCw className="size-4 animate-spin" /> : <Play className="size-4" />}
                  <span>Run Full Pipeline (Stage A → C)</span>
                </button>

                <button
                  onClick={() => handleRunPipeline("ingest-feeds")}
                  disabled={executing || !selectedCampaignId}
                  className="flex items-center justify-center gap-1.5 rounded-lg border border-cyan-500/30 bg-cyan-500/10 py-2 text-xs font-medium text-cyan-600 dark:text-cyan-400 transition-colors hover:bg-cyan-500/20 disabled:opacity-50"
                >
                  <Rss className="size-3.5 text-cyan-500" />
                  <span>Feeds: Abuse.ch</span>
                </button>

                <button
                  onClick={() => handleRunPipeline("ingest")}
                  disabled={executing || !selectedCampaignId}
                  className="flex items-center justify-center gap-1.5 rounded-lg border border-border bg-background py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-50"
                >
                  <Download className="size-3.5" />
                  <span>Stage A: Ingest Only</span>
                </button>

                <button
                  onClick={() => handleRunPipeline("pivot")}
                  disabled={executing || !selectedCampaignId}
                  className="flex items-center justify-center gap-1.5 rounded-lg border border-border bg-background py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-50"
                >
                  <GitBranch className="size-3.5 text-cyan-500" />
                  <span>Stage B: Pivot Only</span>
                </button>

                <button
                  onClick={() => handleRunPipeline("report")}
                  disabled={executing || !selectedCampaignId}
                  className="flex items-center justify-center gap-1.5 rounded-lg border border-border bg-background py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-50"
                >
                  <FileText className="size-3.5 text-amber-500" />
                  <span>Stage C: Report Only</span>
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* Real-time Execution Terminal */}
        <ExecutionTerminal logs={logs} executing={executing} onStop={stopExecution} />

        {/* Findings & Output Reports Tab Navigation */}
        <section className="space-y-4">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div className="flex items-center gap-4">
              <button
                onClick={() => setActiveTab("findings")}
                className={`text-sm font-semibold transition-colors pb-1 border-b-2 ${
                  activeTab === "findings"
                    ? "border-cyan-500 text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                Discovered Domains ({findings.length})
              </button>
              <button
                onClick={() => setActiveTab("reports")}
                className={`text-sm font-semibold transition-colors pb-1 border-b-2 ${
                  activeTab === "reports"
                    ? "border-cyan-500 text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                Report Browser & Stats
              </button>
            </div>
          </div>

          {activeTab === "findings" ? (
            <FindingsTable findings={findings} selectedCampaignId={selectedCampaignId} />
          ) : (
            <ReportViewer
              reportList={reportList}
              currentReport={currentReport}
              onSelectReportDir={fetchReports}
              pipeline="wp-hunter"
            />
          )}
        </section>
      </main>
    </div>
  )
}
