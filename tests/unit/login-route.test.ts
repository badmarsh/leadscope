import { describe, it, expect } from 'vitest'
import { POST } from '@/app/api/login/route'

describe('Login API Route', () => {
  it('returns 400 when body is invalid JSON', async () => {
    const req = new Request('http://localhost:3000/api/login', {
      method: 'POST',
      body: 'invalid-json',
    })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const json = await res.json()
    expect(json.error).toBe('Invalid JSON body')
  })

  it('returns 400 when password is missing', async () => {
    const req = new Request('http://localhost:3000/api/login', {
      method: 'POST',
      body: JSON.stringify({}),
    })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const json = await res.json()
    expect(json.error).toBe('Password is required')
  })

  it('returns 500 when DASHBOARD_PASSWORD_HASH environment variable is missing', async () => {
    const originalHash = process.env.DASHBOARD_PASSWORD_HASH
    delete process.env.DASHBOARD_PASSWORD_HASH

    const req = new Request('http://localhost:3000/api/login', {
      method: 'POST',
      body: JSON.stringify({ password: 'any_password' }),
    })
    const res = await POST(req)
    expect(res.status).toBe(500)
    const json = await res.json()
    expect(json.error).toBe('Server misconfigured')

    process.env.DASHBOARD_PASSWORD_HASH = originalHash
  })
})
