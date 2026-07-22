'use client'

import { useEffect } from 'react'

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // Log error to client error monitoring
    console.error('Unhandled App Router Error:', error)
  }, [error])

  return (
    <div className="flex min-h-[400px] flex-col items-center justify-center space-y-4 text-center p-6">
      <div className="rounded-full bg-red-500/10 p-3 text-red-500">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-8 w-8"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
      </div>
      <h2 className="text-xl font-bold text-slate-100">Something went wrong</h2>
      <p className="max-w-md text-sm text-slate-400">
        An unexpected error occurred while loading this section. Please try again.
      </p>
      <button
        onClick={() => reset()}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
      >
        Try Again
      </button>
    </div>
  )
}
