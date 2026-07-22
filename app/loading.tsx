export default function Loading() {
  return (
    <div className="flex min-h-[400px] w-full flex-col items-center justify-center space-y-4">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-700 border-t-blue-500" />
      <p className="text-sm font-medium text-slate-400">Loading dashboard...</p>
    </div>
  )
}
