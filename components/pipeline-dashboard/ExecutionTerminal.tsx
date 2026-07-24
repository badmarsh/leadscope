"use client"

import React, { useRef, useEffect, useState } from "react"
import { Terminal, Copy, Check, RefreshCw, XCircle } from "lucide-react"

interface ExecutionTerminalProps {
  logs: string
  executing: boolean
  onStop?: () => void
}

export function ExecutionTerminal({ logs, executing, onStop }: ExecutionTerminalProps) {
  const terminalRef = useRef<HTMLPreElement | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight
    }
  }, [logs, executing])

  if (!logs && !executing) {
    return null
  }

  const handleCopy = () => {
    if (!logs) return
    navigator.clipboard.writeText(logs)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <section className="rounded-xl border border-border bg-card p-4 space-y-2 shadow-sm">
      <div className="flex items-center justify-between border-b border-border pb-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
          <Terminal className="size-4 text-cyan-500" />
          <span>Pipeline Real-Time Log Stream</span>
          {executing ? (
            <span className="inline-flex items-center gap-1 rounded bg-amber-500/15 px-2 py-0.5 font-mono text-[10px] text-amber-600 dark:text-amber-400 font-semibold border border-amber-500/20">
              <RefreshCw className="size-3 animate-spin" /> RUNNING
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded bg-emerald-500/15 px-2 py-0.5 font-mono text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold border border-emerald-500/20">
              IDLE
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {executing && onStop && (
            <button
              onClick={onStop}
              className="flex items-center gap-1 px-2 py-1 rounded bg-destructive/10 border border-destructive/30 text-destructive text-[11px] font-semibold hover:bg-destructive/20 transition-colors"
            >
              <XCircle className="size-3" />
              <span>Stop</span>
            </button>
          )}

          {logs && (
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 px-2 py-1 rounded border border-border bg-background text-[11px] text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              {copied ? <Check className="size-3 text-emerald-500" /> : <Copy className="size-3" />}
              <span>{copied ? "Copied" : "Copy"}</span>
            </button>
          )}
        </div>
      </div>

      <pre
        ref={terminalRef}
        className="max-h-64 overflow-y-auto rounded-lg bg-zinc-950 p-3.5 font-mono text-[11px] leading-relaxed text-emerald-400 whitespace-pre-wrap selection:bg-emerald-900 selection:text-emerald-100"
      >
        {logs || "[Waiting for pipeline stdout/stderr stream...]"}
        {executing && <span className="inline-block size-2 bg-emerald-400 animate-pulse ml-1" aria-hidden="true" />}
      </pre>
    </section>
  )
}
