import { ImageResponse } from 'next/og'

import { siteConfig } from '@/lib/constants/site'

export const alt = `${siteConfig.name} — ${siteConfig.tagline}`
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

export default async function OpengraphImage() {
  return new ImageResponse(
    <div
      style={{
        display: 'flex',
        height: '100%',
        width: '100%',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 48,
        background: '#16283f',
        padding: 72,
        color: '#f5f4f1',
        fontFamily: 'serif',
      }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}
      >
        <div style={{ display: 'flex', fontSize: 56, fontWeight: 600 }}>
          {siteConfig.name}
        </div>
        <div style={{ display: 'flex', fontSize: 28, opacity: 0.85 }}>
          {siteConfig.tagline}
        </div>
        <div style={{ display: 'flex', fontSize: 20, opacity: 0.7 }}>
          Book a consultation online
        </div>
      </div>
    </div>,
    size
  )
}
