/**
 * lib/campaigns.ts — Single source of truth for campaign slug ↔ DB ID mapping.
 * Import from here instead of duplicating the map in multiple files (M3).
 */
import type { CampaignId } from "@/lib/leads-data"

/** Maps campaign slug strings (including aliases) to database integer IDs. */
export const CAMPAIGN_SLUG_TO_ID: Record<string, number> = {
  jenex: 1,
  "shoe-photo": 2,
  "wp-remediation": 3,
  // Legacy aliases kept for backward compat
  "jenex-hu-hvac": 1,
  "shoe-photo-upgrade": 2,
  "wp-remediation-wp": 3,
  "small-eshops-boutiques": 2,
}

/** Maps database campaign IDs to the frontend CampaignId enum value. */
export const DB_ID_TO_CAMPAIGN: Record<number, CampaignId> = {
  1: "jenex",
  2: "shoe-photo",
  3: "wp-remediation",
}

/** Maps CampaignId to database integer ID. */
export const CAMPAIGN_TO_DB_ID: Record<CampaignId, number> = {
  jenex: 1,
  "shoe-photo": 2,
  "wp-remediation": 3,
}
