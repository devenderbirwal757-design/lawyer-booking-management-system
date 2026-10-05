import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axe from 'axe-core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BookingWizard } from '@/components/booking/booking-wizard'
import { useBookingStore } from '@/features/booking/store'
import { addDaysKey, todayKey } from '@/lib/utils/dates'

const replace = vi.fn()
const requestOtp = vi.fn(async () => undefined)
const verifyOtp = vi.fn(async () => ({ access: 'a', refresh: 'r' }))

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(''),
  useRouter: () => ({ replace, push: vi.fn(), back: vi.fn() }),
}))

vi.mock('@/features/services/api', () => ({
  useActiveServices: () => ({
    isLoading: false,
    isError: false,
    data: {
      count: 1,
      page: 1,
      page_size: 20,
      num_pages: 1,
      next: null,
      previous: null,
      results: [
        {
          id: 'svc-1',
          slug: 'consultation-30-minutes',
          name: 'Consultation — 30 minutes',
          description: 'A first call to understand the matter.',
          duration_minutes: 30,
          buffer_before_minutes: 0,
          buffer_after_minutes: 5,
          // The API sends price_amount as a decimal string; the zod schema
          // coerces it, so the mocked hook must hand back the coerced shape.
          price_amount: 1500,
          currency: 'INR',
          requires_payment: true,
        },
      ],
    },
  }),
}))

vi.mock('@/features/auth/api', () => ({
  requestOtp: (...args: unknown[]) => requestOtp(...(args as [])),
  verifyOtp: (...args: unknown[]) => verifyOtp(...(args as [])),
}))

function renderWizard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <BookingWizard />
    </QueryClientProvider>
  )
}

async function expectNoSeriousViolations(node: HTMLElement) {
  const results = await axe.run(node, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
  })
  const serious = results.violations.filter((v) =>
    ['serious', 'critical'].includes(v.impact ?? '')
  )
  expect(serious.map((v) => `${v.id}: ${v.help}`)).toEqual([])
}

describe('assembled booking wizard, keyboard only', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.sessionStorage.clear()
    useBookingStore.getState().reset()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        const body = url.includes('/availability/dates')
          ? { dates: [addDaysKey(todayKey(), 1), addDaysKey(todayKey(), 2)] }
          : { slots: ['10:00', '10:30', '11:00'] }
        return {
          ok: true,
          status: 200,
          json: async () => body,
          text: async () => JSON.stringify(body),
        } as unknown as Response
      })
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('walks service -> date -> slot -> details -> OTP using the keyboard alone', async () => {
    const user = userEvent.setup()
    renderWizard()

    // Step 1 — reach the service card without touching the mouse.
    const service = await screen.findByRole('button', {
      name: /Consultation — 30 minutes/,
    })
    service.focus()
    expect(service).toHaveFocus()

    await user.keyboard('{Enter}')
    await waitFor(() => expect(replace).toHaveBeenCalled())
    expect(useBookingStore.getState().serviceId).toBe('svc-1')

    // Tab to Continue and activate it.
    const continueToSchedule = screen.getByRole('button', {
      name: /Choose date & time/,
    })
    continueToSchedule.focus()
    await user.keyboard('{Enter}')

    // Step 2 — pick a date from the date strip, keyboard only.
    const dateGroup = await screen.findByRole('radiogroup', { name: 'Choose a date' })
    const dayButtons = within(dateGroup).getAllByRole('radio')
    const targetDay = dayButtons[1]
    targetDay.focus()
    await user.keyboard('{Enter}')

    await waitFor(() =>
      expect(useBookingStore.getState().date).toBeTruthy()
    )
    // Choosing a date clears any slot, so `startAt` is an empty string here.
    expect(useBookingStore.getState().startAt).toBe('')

    // Step 2b — the slot grid owns arrow-key navigation via a roving tabindex.
    const slotGroup = await screen.findByRole('radiogroup', { name: 'Choose a time' })
    const slots = within(slotGroup).getAllByRole('radio')
    expect(slots.length).toBeGreaterThan(1)

    slots[0].focus()
    expect(slots[0]).toHaveFocus()
    await user.keyboard('{ArrowRight}')
    expect(slots[1]).toHaveFocus()
    await user.keyboard('{Enter}')

    await waitFor(() =>
      expect(useBookingStore.getState().startAt).toBeTruthy()
    )
    expect(useBookingStore.getState().startAt).not.toBe('')

    const scheduleContinue = screen.getByRole('button', { name: /^Continue$/ })
    expect(scheduleContinue).toBeEnabled()
    scheduleContinue.focus()
    await user.keyboard('{Enter}')

    // Step 3 — details form, filled by keyboard only.
    await screen.findByRole('heading', { name: 'Your details' })

    const nameField = screen.getByLabelText('Full name')
    nameField.focus()
    expect(nameField).toHaveFocus()
    await user.keyboard('Asha Rao')

    const phoneField = screen.getByLabelText('Mobile number')
    phoneField.focus()
    await user.keyboard('9876543210')

    const submit = screen.getByRole('button', { name: 'Send verification code' })
    submit.focus()
    await user.keyboard('{Enter}')

    // The OTP box takes over and requests a code on mount.
    await screen.findByRole('heading', { name: 'Verify your number' })
    await waitFor(() => expect(requestOtp).toHaveBeenCalledWith('9876543210'))
    const otpBoxes = await screen.findAllByRole('textbox')
    expect(otpBoxes.length).toBeGreaterThan(0)

    const firstBox = otpBoxes[0]
    firstBox.focus()
    expect(firstBox).toHaveFocus()
    await user.keyboard('123456')

    await waitFor(() => expect(verifyOtp).toHaveBeenCalled())

    // Reaching step 4 means the draft carried through every transition.
    await waitFor(() => expect(useBookingStore.getState().step).toBe(3))
    expect(useBookingStore.getState().details.phone).toBe('9876543210')
  })

  it('has no serious axe violations on the service or details steps', async () => {
    const user = userEvent.setup()
    const { container } = renderWizard()

    await screen.findByRole('button', { name: /Consultation — 30 minutes/ })
    await expectNoSeriousViolations(container)

    await user.click(screen.getByRole('button', { name: /Consultation — 30 minutes/ }))
    await user.click(screen.getByRole('button', { name: /Choose date & time/ }))

    const dateGroup = await screen.findByRole('radiogroup', { name: 'Choose a date' })
    await user.click(within(dateGroup).getAllByRole('radio')[1])
    const slotGroup = await screen.findByRole('radiogroup', { name: 'Choose a time' })
    await user.click(within(slotGroup).getAllByRole('radio')[0])
    await user.click(screen.getByRole('button', { name: /^Continue$/ }))

    await screen.findByRole('heading', { name: 'Your details' })
    await expectNoSeriousViolations(container)
  })

  it('keeps forward steps disabled until the current step is valid', async () => {
    const user = userEvent.setup()
    renderWizard()

    const service = await screen.findByRole('button', {
      name: /Consultation — 30 minutes/,
    })
    await user.click(service)

    // Continue is enabled only once a service is chosen.
    expect(screen.getByRole('button', { name: /Choose date & time/ })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: /Choose date & time/ }))

    // With no slot chosen, Continue must stay disabled.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^Continue$/ })).toBeDisabled()
    )
  })
})
