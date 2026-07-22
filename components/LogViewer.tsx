'use client'

import { useState, useEffect, useRef } from 'react'
import { Terminal, X } from 'lucide-react'

export function LogViewer() {
  const [isOpen, setIsOpen] = useState(false)
  const [logs, setLogs] = useState<string>('Initializing logs...')
  const endRef = useRef<HTMLDivElement>(null)

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

  useEffect(() => {
    if (isOpen && endRef.current) {
      endRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, isOpen])

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end">
      {isOpen ? (
        <div className="w-[600px] h-[400px] bg-slate-950 border border-slate-800 rounded-lg shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-bottom-2 fade-in duration-200">
          <div className="flex justify-between items-center bg-slate-900 px-3 py-2 border-b border-slate-800">
            <div className="flex items-center space-x-2">
              <Terminal className="h-4 w-4 text-emerald-400" />
              <span className="text-sm font-medium text-slate-200">System Logs</span>
            </div>
            <button 
              onClick={() => setIsOpen(false)}
              className="text-slate-400 hover:text-white transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex-1 p-3 overflow-y-auto bg-slate-950 font-mono text-xs text-emerald-400 whitespace-pre-wrap break-all leading-relaxed">
            {logs}
            <div ref={endRef} />
          </div>
        </div>
      ) : (
        <button
          onClick={() => setIsOpen(true)}
          className="flex items-center space-x-2 bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 rounded-full border border-slate-700 shadow-lg transition-all"
        >
          <Terminal className="h-4 w-4" />
          <span className="text-sm font-medium">View Logs</span>
        </button>
      )}
    </div>
  )
}
