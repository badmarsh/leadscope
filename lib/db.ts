/**
 * lib/db.ts — Postgres pool for Next.js API routes.
 * Uses the pg package with a singleton pool pattern safe for Next.js HMR.
 */
import { Pool } from "pg"

const globalForPg = global as unknown as { pgPool: Pool | undefined }

export const pool: Pool =
  globalForPg.pgPool ??
  new Pool({
    connectionString: process.env.DATABASE_URL,
    max: parseInt(process.env.PG_POOL_MAX ?? "10", 10),
    idleTimeoutMillis: parseInt(process.env.PG_POOL_IDLE_TIMEOUT_MS ?? "30000", 10),
    connectionTimeoutMillis: parseInt(process.env.PG_CONN_TIMEOUT_MS ?? "5000", 10),
  })

globalForPg.pgPool = pool

export async function query<T extends object = Record<string, unknown>>(
  text: string,
  values?: unknown[],
): Promise<T[]> {
  const result = await pool.query(text, values)
  return result.rows as T[]
}

export async function queryOne<T extends object = Record<string, unknown>>(
  text: string,
  values?: unknown[],
): Promise<T | null> {
  const result = await pool.query(text, values)
  return (result.rows[0] as T) ?? null
}
