import type { MetadataRoute } from 'next'

import { siteConfig } from '@/lib/constants/site'

import { getActiveServices } from '@/features/services/server-queries'

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const lastModified = new Date()

  const staticRoutes: MetadataRoute.Sitemap = [
    { url: siteConfig.url, lastModified },
    { url: `${siteConfig.url}/services`, lastModified },
    { url: `${siteConfig.url}/terms`, lastModified },
    { url: `${siteConfig.url}/privacy`, lastModified },
  ]

  const result = await getActiveServices()
  if (!result.ok) {
    return staticRoutes
  }

  const serviceRoutes: MetadataRoute.Sitemap = result.services.map(
    (service) => ({
      url: `${siteConfig.url}/services/${service.slug}`,
      lastModified,
    })
  )

  return [...staticRoutes, ...serviceRoutes]
}
