import { describe, it, expect } from 'vitest'
import { NextRequest } from 'next/server'
import { middleware } from '@/middleware'

describe('Middleware Session Gate', () => {
  it('allows access to public paths without session cookie', async () => {
    const req = new NextRequest('http://localhost:3000/api/login')
    const res = await middleware(req)
    expect(res.status).toBe(200)
  })

  it('returns 401 for unauthorized API requests', async () => {
    const req = new NextRequest('http://localhost:3000/api/leads')
    const res = await middleware(req)
    expect(res.status).toBe(401)
    const json = await res.json()
    expect(json).toEqual({ error: 'Unauthorized' })
  })

  it('redirects unauthenticated page requests to /login', async () => {
    const req = new NextRequest('http://localhost:3000/dashboard')
    const res = await middleware(req)
    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toBe('http://localhost:3000/login')
  })
})
