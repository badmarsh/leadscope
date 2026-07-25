import { describe, it, expect, vi, beforeEach } from 'vitest'
import { POST } from '../../app/api/wp-hunter/run/route'
import fs from 'fs/promises'
import * as child_process from 'child_process'

// Mock dependencies
vi.mock('fs/promises', () => {
  return {
    default: {
      writeFile: vi.fn().mockResolvedValue(undefined),
      unlink: vi.fn().mockResolvedValue(undefined)
    }
  }
})

const mockedExecAsync = vi.fn().mockResolvedValue({ stdout: 'mocked stdout', stderr: '' })

vi.mock('util', async (importOriginal) => {
  const actual = await importOriginal<typeof import('util')>()
  return {
    ...actual,
    promisify: () => mockedExecAsync
  }
})

vi.mock('child_process', async (importOriginal) => {
  const actual = await importOriginal<typeof import('child_process')>()
  return {
    ...actual,
    exec: vi.fn(),
    spawn: vi.fn(),
  }
})

describe('POST /api/wp-hunter/run', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should return 400 if stage is missing', async () => {
    const req = new Request('http://localhost/api/wp-hunter/run', {
      method: 'POST',
      body: JSON.stringify({ campaignId: 'test-campaign' })
    })
    
    const res = await POST(req)
    expect(res.status).toBe(400)
  })

  it('should return 400 if campaignId is missing', async () => {
    const req = new Request('http://localhost/api/wp-hunter/run', {
      method: 'POST',
      body: JSON.stringify({ stage: 'run' })
    })
    
    const res = await POST(req)
    expect(res.status).toBe(400)
  })

  it('should call exec with correct arguments for run stage', async () => {
    const req = new Request('http://localhost/api/wp-hunter/run', {
      method: 'POST',
      body: JSON.stringify({ stage: 'run', campaignId: 'test-campaign', forceStale: true })
    })
    
    const res = await POST(req)
    expect(res.status).toBe(200)
    
    expect(mockedExecAsync).toHaveBeenCalled()
    const callArgs = (mockedExecAsync as any).mock.calls[0][0]
    expect(callArgs).toContain('-m wp_hunter.cli run --campaign test-campaign --i-know-this-is-stale')
  })

  it('should create and delete temp file if pasteContent is provided', async () => {
    const req = new Request('http://localhost/api/wp-hunter/run', {
      method: 'POST',
      body: JSON.stringify({ stage: 'run', campaignId: 'test-campaign', pasteContent: 'test content' })
    })
    
    const res = await POST(req)
    expect(res.status).toBe(200)
    
    expect(fs.writeFile).toHaveBeenCalled()
    expect(fs.unlink).toHaveBeenCalled()
  })
})
