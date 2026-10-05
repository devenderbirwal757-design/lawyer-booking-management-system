import { describe, expect, it } from 'vitest'

import { siteConfig } from '@/lib/constants/site'
import { API_BASE_URL } from '@/lib/api/client'

describe('deployment env wiring', () => {
  it('derives the API base URL and strips trailing slashes', () => {
    expect(API_BASE_URL.startsWith('http')).toBe(true)
    expect(API_BASE_URL.endsWith('/')).toBe(false)
  })

  it('falls back to a parseable app URL for metadata and sitemap', () => {
    expect(() => new URL(siteConfig.url)).not.toThrow()
  })

  it('keeps the API path suffix the backend plan requires', () => {
    const configured = process.env.NEXT_PUBLIC_API_URL
    if (configured) {
      expect(API_BASE_URL.endsWith('/api/v1')).toBe(true)
    }
  })
})
