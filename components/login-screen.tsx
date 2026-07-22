"use client"

import { useState } from "react"
import { Radar } from "lucide-react"
import { Button } from "@/components/ui/button"

export function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const r = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      })
      if (r.ok) {
        onLogin()
      } else {
        const data = await r.json()
        setError(data.error ?? "Login failed")
      }
    } catch {
      setError("Network error — try again")
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex size-11 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Radar className="size-5" aria-hidden="true" />
          </div>
          <div className="text-center">
            <h1 className="text-lg font-semibold tracking-tight text-foreground">Leadscope</h1>
            <p className="text-sm text-muted-foreground">Sign in to review campaign leads</p>
          </div>
        </div>

        <form
          id="login-form"
          className="flex flex-col gap-4 rounded-xl border border-border bg-card p-6"
          onSubmit={handleSubmit}
        >
          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-sm font-medium text-foreground">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/50"
            />
          </div>

          {error && (
            <p id="login-error" className="text-sm text-destructive">{error}</p>
          )}

          <Button id="login-submit" type="submit" className="mt-1 w-full" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </Button>
          <p className="text-center font-mono text-xs text-muted-foreground">v0.4.1 · internal tool</p>
        </form>
      </div>
    </main>
  )
}
