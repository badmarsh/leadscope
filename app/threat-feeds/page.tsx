"use client"

import { useState, useEffect, useRef } from "react"
import Link from "next/link"
import {
  ShieldAlert,
  Crosshair,
  ArrowLeft,
  Rss,
  Activity,
  CheckCircle2,
  AlertTriangle,
  Play,
  RefreshCw
} from "lucide-react"

import { CtTickerWidget } from "@/components/pipeline-dashboard/CtTickerWidget"
import { ExecutionTerminal } from "@/components/pipeline-dashboard/ExecutionTerminal"
import { PipelineCampaign } from "@/components/pipeline-dashboard/CampaignCard"

export default function ThreatFeedsPage() {
  const [wpCampaigns, setWpCampaigns] = useState<PipelineCampaign[]>([])
  const [seoCampaigns, setSeoCampaigns] = useState<PipelineCampaign[]>([])
  
  const [executing, setExecuting] = useState<boolean>(false)
  const [logs, setLogs] = useState<string>("")
  
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    fetchCampaigns()
  }, [])

  const fetchCampaigns = async () => {
    try {
      const [wpRes, seoRes] = await Promise.all([
        fetch("/api/wp-hunter/campaigns"),
        fetch("/api/seo-spam-hunter/campaigns")
      ])
      const wpData = await wpRes.json()
      const seoData = await seoRes.json()
      
      if (wpData.campaigns) setWpCampaigns(wpData.campaigns)
      if (seoData.campaigns) setSeoCampaigns(seoData.campaigns)
    } catch (err) {
      console.error("Failed to fetch campaigns:", err)
    }
  }

  const stopExecution = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setExecuting(false)
  }

  const handleIngestAllFeeds = async () => {
    stopExecution()
    setExecuting(true)
    setLogs(`[${new Date().toLocaleTimeString()}] Starting global feed ingestion...\n\n`)

    const activeWp = wpCampaigns.filter(c => !c.is_template && !c.is_stale)
    const activeSeo = seoCampaigns.filter(c => !c.is_template && !c.is_stale)

    const allTasks = [
      ...activeWp.map(c => ({ pipeline: "wp-hunter", campaignId: c.id })),
      ...activeSeo.map(c => ({ pipeline: "seo-spam-hunter", campaignId: c.id }))
    ]

    if (allTasks.length === 0) {
      setLogs(prev => prev + "No active campaigns found to ingest feeds for.\n[Execution finished]")
      setExecuting(false)
      return
    }

    setLogs(prev => prev + `Found ${allTasks.length} active campaigns. Queuing ingestion tasks...\n\n`)

    for (const task of allTasks) {
      setLogs(prev => prev + `\n--- Starting ingest-feeds for ${task.pipeline} : ${task.campaignId} ---\n`)
      
      await new Promise<void>((resolve) => {
        const params = new URLSearchParams({ stage: "ingest-feeds", campaignId: task.campaignId })
        const es = new EventSource(`/api/${task.pipeline}/run?${params.toString()}`)
        eventSourceRef.current = es

        es.onmessage = (e) => {
          if (e.data === "[DONE]") {
            es.close()
            resolve()
          } else {
            setLogs((prev) => prev + e.data + "\n")
          }
        }

        es.onerror = () => {
          es.close()
          setLogs((prev) => prev + "\n[Stream connection closed with error]\n")
          resolve()
        }
      })
    }

    setLogs((prev) => prev + "\n[Global Feed Ingestion Finished]")
    setExecuting(false)
  }

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
              <div className="flex size-7 items-center justify-center rounded-md bg-violet-500/15 text-violet-600 dark:text-violet-400">
                <Rss className="size-4" />
              </div>
              <h1 className="text-base font-bold tracking-tight">Threat Intelligence Feeds</h1>
              <span className="rounded-full bg-primary/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-primary">
                Global
              </span>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        
        {/* Global Feeds Overview */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-2">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold">URLhaus & ThreatFox</span>
              <Activity className="size-4 text-emerald-500" />
            </div>
            <p className="text-2xl font-bold tracking-tight">Active</p>
            <p className="text-[11px] text-muted-foreground">Ready for campaign polling</p>
          </div>

          <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-2">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold">Active Campaigns</span>
              <Crosshair className="size-4 text-cyan-500" />
            </div>
            <p className="text-2xl font-bold tracking-tight">
              {wpCampaigns.filter(c => !c.is_stale).length + seoCampaigns.filter(c => !c.is_stale).length}
            </p>
            <p className="text-[11px] text-muted-foreground">Eligible for feed ingestion</p>
          </div>

          <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-2">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold">CT Monitor</span>
              <ShieldAlert className="size-4 text-amber-500" />
            </div>
            <p className="text-2xl font-bold tracking-tight">Live</p>
            <p className="text-[11px] text-muted-foreground">Listening for certstream events</p>
          </div>
        </section>

        {/* Action Panel */}
        <section className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-3">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-semibold tracking-tight text-foreground">
                <Rss className="size-4 text-violet-500" />
                Global Feed Ingestion
              </h2>
              <p className="text-xs text-muted-foreground">
                Run feed ingestion across all active campaigns, or monitor Certificate Transparency logs.
              </p>
            </div>
            
            {/* CT Stream Live Ticker Widget */}
            <CtTickerWidget
              selectedCampaignId={seoCampaigns.length > 0 ? seoCampaigns[0].id : ""}
              onFindingsUpdate={() => {}}
            />
          </div>

          <div className="space-y-4">
            <div className="rounded-lg border border-border/80 bg-muted/40 p-4 space-y-3">
              <h3 className="text-sm font-semibold">Ingest All Feeds</h3>
              <p className="text-xs text-muted-foreground">
                This will loop over all active (non-stale) campaigns in both WP Hunter and SEO Spam Hunter, 
                triggering Abuse.ch ingestion sequentially to avoid rate limits.
              </p>
              
              <button
                onClick={handleIngestAllFeeds}
                disabled={executing || (wpCampaigns.length === 0 && seoCampaigns.length === 0)}
                className="flex items-center justify-center gap-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white py-2.5 px-4 text-xs font-semibold shadow transition-colors disabled:opacity-50"
              >
                {executing ? <RefreshCw className="size-4 animate-spin" /> : <Play className="size-4" />}
                <span>Ingest Feeds for All Active Campaigns</span>
              </button>
            </div>
          </div>
        </section>

        {/* Real-time Execution Terminal */}
        <ExecutionTerminal logs={logs} executing={executing} onStop={stopExecution} />

      </main>
    </div>
  )
}
