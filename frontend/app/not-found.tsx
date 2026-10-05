import Link from 'next/link'

import { Button } from '@/components/ui/button'

export default function NotFound() {
  return (
    <div className="mx-auto flex w-full max-w-md flex-col items-center gap-4 py-24 text-center">
      <p className="text-sm font-medium tracking-widest text-muted-foreground uppercase">
        404
      </p>
      <h1 className="font-serif text-2xl font-semibold">Page not found</h1>
      <p className="text-sm text-muted-foreground">
        The page you are looking for may have moved or no longer exists.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <Button asChild>
          <Link href="/">Go to homepage</Link>
        </Button>
        <Button variant="outline" asChild>
          <Link href="/services">Browse services</Link>
        </Button>
      </div>
    </div>
  )
}
