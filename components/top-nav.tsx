"use client"

import { LogOut, Moon, Radar, Settings, Sun, Database, HelpCircle, Webhook, Languages } from "lucide-react"
import { campaigns, type CampaignId } from "@/lib/leads-data"
import { cn } from "@/lib/utils"
import { useTranslation, type Locale } from "@/lib/i18n"

interface TopNavProps {
  activeCampaign: CampaignId
  onCampaignChange: (id: CampaignId) => void
  darkMode: boolean
  onToggleDarkMode: () => void
  onLogout: () => void
  onSettingsOpen: () => void
  onKbOpen?: () => void
  onHelpOpen?: () => void
  onN8nOpen?: () => void
}

export function TopNav({
  activeCampaign,
  onCampaignChange,
  darkMode,
  onToggleDarkMode,
  onLogout,
  onSettingsOpen,
  onKbOpen,
  onHelpOpen,
  onN8nOpen,
}: TopNavProps) {
  const { t, locale, setLocale } = useTranslation()

  const toggleLanguage = () => {
    setLocale(locale === "en" ? "sk" : "en")
  }

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 lg:px-6">
        <div className="flex min-w-0 items-center gap-6">
          <div className="flex shrink-0 items-center gap-2">
            <div className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Radar className="size-4" aria-hidden="true" />
            </div>
            <span className="hidden text-sm font-semibold tracking-tight text-foreground sm:block">
              {t("nav.title")}
            </span>
          </div>

          <nav aria-label="Campaigns" className="min-w-0 overflow-x-auto">
            <div role="tablist" className="flex items-center gap-1">
              {campaigns.map((c) => (
                <button
                  key={c.id}
                  role="tab"
                  aria-selected={activeCampaign === c.id}
                  onClick={() => onCampaignChange(c.id)}
                  className={cn(
                    "inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-3 py-1.5 text-sm transition-colors",
                    activeCampaign === c.id
                      ? "bg-accent font-medium text-accent-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <span className="hidden md:inline">{c.name}</span>
                  <span className="md:hidden">{c.shortName}</span>
                  {c.status === "draft" && (
                    <span className="rounded border border-amber-500/30 bg-amber-500/15 px-1 py-px font-mono text-[10px] font-semibold leading-tight text-amber-700 dark:text-amber-400">
                      DRAFT
                    </span>
                  )}
                  {c.status === "paused" && (
                    <span className="rounded border border-border bg-muted px-1 py-px font-mono text-[10px] font-semibold leading-tight text-muted-foreground">
                      PAUSED
                    </span>
                  )}
                </button>
              ))}
            </div>
          </nav>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <button
            onClick={toggleLanguage}
            title={`Switch to ${locale === "en" ? "Slovak" : "English"}`}
            className="flex h-8 items-center justify-center gap-1 rounded-md px-2 text-xs font-semibold text-muted-foreground transition-colors hover:bg-accent hover:text-foreground uppercase"
          >
            <Languages className="size-4" />
            {locale}
          </button>
          
          {onKbOpen && (
            <button
              onClick={onKbOpen}
              aria-label="Knowledge Base"
              className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <Database className="size-4" />
            </button>
          )}
          {onN8nOpen && (
            <button
              onClick={onN8nOpen}
              aria-label={t("nav.n8n")}
              className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <Webhook className="size-4" />
            </button>
          )}
          {onHelpOpen && (
            <button
              onClick={onHelpOpen}
              aria-label="Help & Documentation"
              className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <HelpCircle className="size-4" />
            </button>
          )}
          <button
            onClick={onSettingsOpen}
            aria-label="Campaign settings"
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <Settings className="size-4" />
          </button>
          <button
            onClick={onToggleDarkMode}
            aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            {darkMode ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
          <button
            onClick={onLogout}
            aria-label="Sign out"
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <LogOut className="size-4" />
          </button>
        </div>
      </div>
    </header>
  )
}
