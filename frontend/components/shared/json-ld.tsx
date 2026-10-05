import { toJsonLd } from '@/lib/utils/json-ld'

export function JsonLd({ data }: { data: Record<string, unknown> }) {
  const json = toJsonLd(data)
  return <script type="application/ld+json">{json}</script>
}
