# v0 prompt — lead-review dashboard GUI prototype

**Companion to:** `leadgen-platform-coding-agent-megaprompt.md`. This file stands alone — it's meant for v0 (Vercel's AI UI generator, at v0.app), not a coding agent.

## How to use this

1. Paste the prompt below into v0.app in one shot. v0 outputs Next.js + React + Tailwind + shadcn/ui with a live preview.
2. Treat the result as a **prototype with mock data** — it won't talk to your real Postgres/FastAPI backend. That wiring happens later, in Part 4b of the coding-agent megaprompt.
3. Once you're happy with it, export the generated project (v0 offers a way to download the code or sync it to GitHub — the exact mechanism has shifted around in v0's UI over time, so use whatever your current version offers) as a zip.
4. Hand that zip, alongside `leadgen-platform-coding-agent-megaprompt.md` and your populated `.env` file, to your coding agent. That document's Part 4b picks up from exactly this point.

**On v0's credit system:** it's metered per token (input + output), and every "now fix this" follow-up costs more, same as the initial generation — so it's worth putting effort into getting this one prompt right rather than iterating in small steps afterward. If your v0 tier lets you pick a model, the mid tier is usually enough for a first full-page build; save a top tier for a polish pass if you need one. Verify the current pricing/tier UI yourself before assuming any of this still matches exactly — v0's tier system changes over time.

---

## The prompt

```
Build a lead-review dashboard for a B2B lead-generation tool, as a
Next.js app using Tailwind and shadcn/ui components.

Requirements:
- A simple login screen (email/password style form, doesn't need to
  be functional yet — just the visual) gating the rest of the app
- Top nav with a campaign switcher (tabs or dropdown), three campaigns:
  "JENEX HVAC (Hungary)", "Shoe Photo Upgrade", "WP Remediation"
- Header stats row for the selected campaign: counts of pending
  review, approved, rejected, and enrichment-failed leads, plus a
  small "usage this month" readout (e.g. "$4.20 OpenRouter · 340/1000
  PublicWWW queries")
- Main content: a sortable table of leads pending review for the
  selected campaign. Columns: company name, domain (as a link),
  opportunity score 0-100 (colored badge or progress bar), status,
  date found. Default sort: score descending. Include a filter to
  switch to viewing "enrichment failed" leads separately from
  "pending review"
- Clicking a row opens a right-side detail drawer showing:
  - Company name, domain link, full rationale text
  - An evidence section that adapts by campaign:
    - JENEX: a list of clickable evidence URLs
    - Shoe Photo Upgrade: a small image gallery of the scraped
      product photos
    - WP Remediation: a badge naming the matched malware family, a
      link to the source security-blog post, and a "last confirmed
      present" timestamp
  - Approve / Reject buttons and an optional free-text note field
- Clean, modern, slightly technical aesthetic: dark mode toggle,
  monospace styling for domains and scores, color coding (green =
  approved, red = rejected, amber = pending, gray = enrichment failed)
- Use realistic mock data for now (a handful of sample leads spread
  across all three campaigns) — no real backend required yet
- Responsive, optimized primarily for a laptop-width screen
```
