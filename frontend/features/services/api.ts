import { useQuery } from '@tanstack/react-query'

import {
  serviceListPageSchema,
  serviceSchema,
  type Service,
} from '@/features/services/schema'

import { api } from '@/lib/api/client'
import { endpoints } from '@/lib/api/endpoints'
import { queryKeys } from '@/lib/api/query-keys'

// The backend serialises `price_amount` as a decimal *string* ("1500.00"), so a
// bare `api.get<Service[]>` type assertion silently hands `"1500.00"` to
// `formatMoney`, which throws and takes the whole booking page down to its
// error boundary. Parse every response instead of trusting the generic.
/**
 * `initialData` lets the caller hand over a server-fetched list so the first
 * paint already contains it. `/book` passes the result of the server query:
 * without it the wizard rendered an empty step 1 and only filled in once the
 * client bundle had booted and the API had answered, which made the service
 * descriptions - the largest text on the page - arrive long after first paint
 * and pushed LCP to ~3.8s.
 */
export function useActiveServices(initialData?: { results: Service[] }) {
  return useQuery({
    queryKey: queryKeys.services.list('active'),
    queryFn: () =>
      api.get<{ results: Service[] }>(
        endpoints.services.list({ status: 'active' }),
        { schema: serviceListPageSchema }
      ),
    initialData,
    staleTime: 15_000,
  })
}

export function useService(slug: string) {
  return useQuery({
    queryKey: queryKeys.services.detail(slug),
    queryFn: () =>
      api.get<Service>(endpoints.services.detail(slug), {
        schema: serviceSchema,
      }),
  })
}
