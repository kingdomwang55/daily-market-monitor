import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TradesView from './TradesView.vue'
import { getTrades } from '../api/client'

vi.mock('../api/client', () => ({
  createTrade: vi.fn(),
  getTrades: vi.fn(),
}))

const page = { items: [], total: 40, limit: 20, offset: 0 }

describe('TradesView', () => {
  beforeEach(() => {
    vi.mocked(getTrades).mockReset().mockResolvedValue(page)
  })

  it('applies filters and drives pagination', async () => {
    const wrapper = mount(TradesView, {
      global: { stubs: { RouterLink: true } },
    })
    await flushPromises()

    const inputs = wrapper.findAll('.trade-filter-bar input')
    await inputs[0].setValue('sh510300')
    await inputs[1].setValue('swing')
    await wrapper.find('.trade-filter-bar select').setValue('open')
    await wrapper.find('.trade-filter-bar').trigger('submit')
    await flushPromises()

    expect(getTrades).toHaveBeenLastCalledWith({
      status: 'open', symbol: 'sh510300', strategy: 'swing', limit: 20, offset: 0,
    })

    vi.mocked(getTrades).mockResolvedValue({ ...page, offset: 20 })
    await wrapper.find('button[aria-label="下一页"]').trigger('click')
    await flushPromises()
    expect(getTrades).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 20 }))
  })
})
