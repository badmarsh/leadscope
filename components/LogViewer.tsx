'use client'

import { useState, useEffect, useRef } from 'react'
import { Terminal, X } from 'lucide-react'

export function LogViewer() {
  const [isOpen, setIsOpen] = useState(false)
  const [logs, setLogs] = useState<string>('Initializing logs...')
  const endRef = useRef<HTMLDivElement>(null)

  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)

  useEffect(() => {
    let interval: NodeJS.Timeout

    if (isOpen) {
      const fetchLogs = async () => {
        try {
          const res = await fetch('/api/logs')
          const data = await res.json()
          if (data.logs) {
            setLogs(data.logs)
          }
        } catch (err) {
          console.error('Failed to fetch logs', err)
        }
      }

      fetchLogs()
      interval = setInterval(fetchLogs, 2000)
    }

    return () => {
      if (interval) clearInterval(interval)
    }
  }, [isOpen])

  const handleScroll = () => {
    if (!scrollContainerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current
    const isAtBottom = Math.abs(scrollHeight - scrollTop - clientHeight) < 50
    setAutoScroll(isAtBottom)
  }

  useEffect(() => {
    if (isOpen && autoScroll && endRef.current) {
      endRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, isOpen, autoScroll])

  // Generic Syntax Highlighting parser
  const parseLogLine = (line: string, i: number) => {
    if (!line.trim()) return null;
    
    // Split by generic log tokens (levels, quotes, IPs, status codes, URLs, timestamps)
    const regex = /(ERROR|WARNING|WARN|INFO|DEBUG|"[^"]*"|'[^']*'|\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?\b|\b(?:200 OK|404 Not Found|500 Internal Server Error|successfully)\b|https?:\/\/[^\s]+|^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}(?:,\d+)?)/g;
    
    const parts = line.split(regex);
    const elements = parts.map((part, j) => {
      if (!part) return null;
      if (part === "ERROR" || part === "WARNING" || part === "WARN" || part === "INFO" || part === "DEBUG") {
        let lColor = "text-slate-300";
        if (part === "ERROR") lColor = "text-[#f87171] font-bold";
        if (part === "WARNING" || part === "WARN") lColor = "text-[#fbbf24] font-bold";
        if (part === "INFO") lColor = "text-[#22d3ee] font-bold";
        if (part === "DEBUG") lColor = "text-slate-400 font-bold";
        return <span key={j} className={lColor}>{part}</span>;
      }
      if (part.startsWith('"') || part.startsWith("'")) return <span key={j} className="text-[#fde047]">{part}</span>;
      if (part.match(/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/)) return <span key={j} className="text-[#c084fc]">{part}</span>;
      if (part === "successfully" || part === "200 OK") return <span key={j} className="text-[#4ade80]">{part}</span>;
      if (part === "404 Not Found" || part.includes("500 Internal")) return <span key={j} className="text-[#f87171]">{part}</span>;
      if (part.startsWith("http")) return <a key={j} href={part} target="_blank" rel="noopener noreferrer" className="text-[#60a5fa] hover:underline cursor-pointer">{part}</a>;
      if (part.match(/^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}/)) return <span key={j} className="text-slate-500">{part}</span>;
      return <span key={j} className="text-slate-300">{part}</span>;
    });

    let bgClass = "hover:bg-black/20";
    if (line.includes("ERROR") || line.match(/Traceback/)) {
      bgClass = "bg-[#7f1d1d]/10 hover:bg-[#7f1d1d]/20 border-l-2 border-[#f87171]";
    } else if (line.includes("WARN")) {
      bgClass = "bg-[#78350f]/10 hover:bg-[#78350f]/20 border-l-2 border-[#fbbf24]";
    } else {
      bgClass = "hover:bg-black/20 border-l-2 border-transparent";
    }

    return (
      <div key={i} className={`px-2 py-[2px] font-mono text-[13px] leading-[1.5] break-words whitespace-pre-wrap ${bgClass}`}>
        {elements}
      </div>
    );
  }

  return (
    <>
      <div className="fixed bottom-4 left-4 z-40 flex flex-col items-start">
        {!isOpen && (
          <button
            onClick={() => setIsOpen(true)}
            className="flex items-center space-x-2 bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 rounded-full border border-slate-700 shadow-lg transition-all"
          >
            <Terminal className="h-4 w-4" />
            <span className="text-sm font-medium">View Logs</span>
          </button>
        )}
      </div>

      {isOpen && (
        <>
          <div 
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200" 
            onClick={() => setIsOpen(false)} 
          />
          <div className="fixed inset-x-0 bottom-0 z-50 flex w-full h-[65vh] flex-col bg-[#1e1e1e] shadow-[0_-10px_40px_rgba(0,0,0,0.5)] border-t border-slate-800 animate-in slide-in-from-bottom duration-300">
            <div className="flex items-center justify-between border-b border-[#2d2d2d] px-6 py-2 bg-[#252526] shrink-0">
              <div className="flex items-center gap-3">
                <Terminal className="size-4 text-[#22d3ee]" />
                <h2 className="text-sm font-medium text-slate-200 uppercase tracking-wider">System Logs</h2>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-white"
              >
                <X className="size-4" />
              </button>
            </div>
            
            <div 
              ref={scrollContainerRef}
              onScroll={handleScroll}
              className="flex-1 overflow-y-auto p-4 bg-[#1e1e1e]"
            >
              {logs.split('\n').map((line, i) => parseLogLine(line, i))}
              <div ref={endRef} />
            </div>
          </div>
        </>
      )}
    </>
  )
}
