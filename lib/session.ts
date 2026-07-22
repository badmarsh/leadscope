/**
 * lib/session.ts — iron-session v8 configuration for the dashboard.
 * Single shared password, httpOnly signed cookie.
 */
import { SessionOptions } from "iron-session"

export interface SessionData {
  loggedIn?: boolean
}

const secret = process.env.DASHBOARD_SESSION_SECRET || "complex_32_char_fallback_secret_for_development_mode"

if (process.env.NODE_ENV === "production" && (!process.env.DASHBOARD_SESSION_SECRET || process.env.DASHBOARD_SESSION_SECRET.length < 32)) {
  throw new Error("DASHBOARD_SESSION_SECRET must be set and at least 32 characters long in production.")
}

export const sessionOptions: SessionOptions = {
  cookieName: "leadscope_session",
  password: secret,
  cookieOptions: {
    secure: process.env.NODE_ENV === "production",
    httpOnly: true,
    sameSite: "lax",
  },
}
