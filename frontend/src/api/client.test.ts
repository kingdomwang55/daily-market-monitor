import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createSignalAction, createTrade, getTrades } from './client'

function okJson(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response
}

describe('API client', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('serializes trade filters without empty values', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okJson({ items: [], total: 0, limit: 20, offset: 20 }),
    )

    await getTrades({ status: 'open', symbol: '', strategy: 'breakout', limit: 20, offset: 20 })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/trades?status=open&strategy=breakout&limit=20&offset=20',
      expect.objectContaining({ headers: expect.objectContaining({ Accept: 'application/json' }) }),
    )
  })

  it('sends mutation methods, JSON bodies, and the optional local token', async () => {
    sessionStorage.setItem('market-write-token', 'test-token')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(okJson({ created: true }))

    await createSignalAction(7, { decision: 'watch', reason: 'wait' })
    await createTrade({
      request_id: 'request-001', symbol: 'sh510300', action: 'long', entry_price: 4.1, qty: 100,
    })

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/signals/7/actions', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ decision: 'watch', reason: 'wait' }),
      headers: expect.objectContaining({ 'X-Market-Token': 'test-token', 'Content-Type': 'application/json' }),
    }))
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/trades', expect.objectContaining({ method: 'POST' }))
  })
})
