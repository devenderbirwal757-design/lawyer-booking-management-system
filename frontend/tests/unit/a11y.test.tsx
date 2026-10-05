import { render } from '@testing-library/react'
import axe from 'axe-core'
import { describe, expect, it } from 'vitest'

import { AppointmentTimeline } from '@/components/customer/appointment-timeline'
import { EmptyState } from '@/components/shared/empty-state'
import { ErrorFallback } from '@/components/shared/error-fallback'
import { OfflineBanner } from '@/components/shared/offline-banner'
import { QueryError } from '@/components/shared/query-error'
import {
  AppointmentStatusBadge,
  PaymentStatusBadge,
} from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { DataTable } from '@/components/shared/data-table'
import { Skeleton } from '@/components/ui/skeleton'

async function expectNoSeriousViolations(node: HTMLElement) {
  const results = await axe.run(node, {
    runOnly: {
      type: 'tag',
      values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'],
    },
    rules: {
      // jsdom has no layout engine, so contrast cannot be evaluated here.
      'color-contrast': { enabled: false },
    },
  })
  const serious = results.violations.filter(
    (violation) =>
      violation.impact === 'serious' || violation.impact === 'critical'
  )
  expect(
    serious.map((violation) => `${violation.id}: ${violation.help}`)
  ).toEqual([])
}

describe('axe sweep', () => {
  it('status badges have no serious violations', async () => {
    const { container } = render(
      <div>
        <AppointmentStatusBadge status="CONFIRMED" />
        <AppointmentStatusBadge status="PENDING_PAYMENT" />
        <PaymentStatusBadge status="SUCCESS" />
        <PaymentStatusBadge status="FAILED" />
      </div>
    )
    await expectNoSeriousViolations(container)
  })

  it('empty state has no serious violations', async () => {
    const { container } = render(
      <EmptyState
        title="No appointments yet"
        description="Book a consultation to get started."
        actionLabel="Book now"
        onAction={() => undefined}
      />
    )
    await expectNoSeriousViolations(container)
  })

  it('data table (with content) has no serious violations', async () => {
    const { container } = render(
      <DataTable
        data={[
          { id: '1', client: 'Rahul Kumar', status: 'CONFIRMED' as const },
        ]}
        keyFor={(row) => row.id}
        emptyTitle="No rows"
        columns={[
          { header: 'Client', cell: (row) => row.client },
          { header: 'Status', cell: (row) => row.status },
        ]}
      />
    )
    await expectNoSeriousViolations(container)
  })

  it('error and offline surfaces have no serious violations', async () => {
    const { container } = render(
      <div>
        <ErrorFallback error={new Error('boom')} />
        <QueryError error={new TypeError('Failed to fetch')} />
        <OfflineBanner />
      </div>
    )
    await expectNoSeriousViolations(container)
  })

  it('status timeline has no serious violations', async () => {
    const { container } = render(
      <AppointmentTimeline
        history={[
          {
            from_status: 'PENDING_PAYMENT',
            to_status: 'CONFIRMED',
            actor: 'admin',
            note: 'Payment received',
            created_at: '2026-03-01T10:00:00Z',
          },
        ]}
      />
    )
    await expectNoSeriousViolations(container)
  })

  it('cards and skeletons have no serious violations', async () => {
    const { container } = render(
      <div>
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent>
            <Button>Save</Button>
            <Skeleton className="h-4 w-32" />
          </CardContent>
        </Card>
      </div>
    )
    await expectNoSeriousViolations(container)
  })
})
