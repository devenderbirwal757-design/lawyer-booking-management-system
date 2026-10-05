'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from 'next-themes'
import { useEffect, useState } from 'react'

import { Toaster } from '@/components/ui/sonner'
import { setUnauthorisedHandler } from '@/lib/api/client'

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: true,
          },
        },
      })
  )

  useEffect(() => {
    const handleUnauthorised = () => {
      const isAdmin =
        typeof window !== 'undefined' &&
        window.location.pathname.startsWith('/admin')
      window.location.assign(isAdmin ? '/admin/login' : '/login')
    }
    setUnauthorisedHandler(handleUnauthorised)
    return () => setUnauthorisedHandler(null)
  }, [])

  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="light"
      forcedTheme="light"
      disableTransitionOnChange
    >
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      <Toaster position="bottom-right" closeButton />
    </ThemeProvider>
  )
}
