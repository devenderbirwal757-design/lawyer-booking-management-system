import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useState } from 'react'

import { SlotPicker } from '@/components/booking/slot-picker'
import { OtpInput } from '@/components/shared/otp-input'
import { ConfirmDialog } from '@/components/shared/confirm-dialog'
import { Button } from '@/components/ui/button'
import { addDaysKey, todayKey } from '@/lib/utils/dates'

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
  return Wrapper
}

describe('booking flow keyboard access', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        const body = url.includes('/availability/dates')
          ? { dates: [addDaysKey(todayKey(), 1)] }
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

  it('selects a date and a slot with the keyboard only', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()

    function PickerHarness() {
      const [date, setDate] = useState<string | null>(null)
      const [startAt, setStartAt] = useState<string | null>(null)
      return (
        <SlotPicker
          serviceId="svc-1"
          date={date}
          startAt={startAt}
          onSelect={(nextDate, nextStartAt, label) => {
            setDate(nextDate)
            setStartAt(label || nextStartAt || null)
            onSelect(nextDate, label || nextStartAt, label)
          }}
        />
      )
    }

    render(<PickerHarness />, { wrapper: createWrapper() })

    const tomorrow = addDaysKey(todayKey(), 1)

    // The date strip is a radio group: reach it with Tab and activate with Enter.
    const dateRadios = await screen.findAllByRole('radio')
    const dateRadio = dateRadios[1]
    dateRadio.focus()
    expect(dateRadio).toHaveFocus()
    await user.keyboard('{Enter}')

    await waitFor(() => expect(onSelect).toHaveBeenCalled())
    expect(onSelect.mock.calls[0][0]).toBe(tomorrow)

    // The time group exposes exactly one tab stop (roving tabindex) and arrow
    // keys move between slots.
    const timeGroup = await screen.findByRole('radiogroup', {
      name: 'Choose a time',
    })
    const slots = within(timeGroup).getAllByRole('radio')
    expect(
      slots.filter((slot) => slot.getAttribute('tabindex') === '0')
    ).toHaveLength(1)

    slots[0].focus()
    expect(slots[0]).toHaveFocus()
    await user.keyboard('{ArrowRight}')
    expect(slots[1]).toHaveFocus()
    await user.keyboard(' ')

    await waitFor(() => expect(onSelect.mock.calls.at(-1)?.[0]).toBe(tomorrow))
    const chosen = String(onSelect.mock.calls.at(-1)?.[1])
    expect(chosen).toContain('10:30')
    expect(slots[1]).toHaveAccessibleName(/10:30/)
    await waitFor(() =>
      expect(slots[1]).toHaveAttribute('aria-checked', 'true')
    )
  })

  it('moves focus through the OTP input with the keyboard', async () => {
    const user = userEvent.setup()

    function OtpHarness() {
      const [value, setValue] = useState('')
      return <OtpInput value={value} onValueChange={setValue} />
    }

    render(<OtpHarness />)

    const inputs = screen.getAllByRole('textbox')
    expect(inputs).toHaveLength(6)

    inputs[0].focus()
    await user.keyboard('123456')

    expect(inputs.map((input) => (input as HTMLInputElement).value)).toEqual([
      '1',
      '2',
      '3',
      '4',
      '5',
      '6',
    ])
  })

  it('closes the confirmation dialog with Escape', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    const onConfirm = vi.fn()

    render(
      <ConfirmDialog
        open
        onOpenChange={onOpenChange}
        title="Confirm booking"
        onConfirm={onConfirm}
      />
    )

    const confirm = screen.getByRole('button', { name: 'Confirm' })
    confirm.focus()
    expect(confirm).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('activates a focused button with Enter', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Continue</Button>)

    await user.tab()
    expect(screen.getByRole('button', { name: 'Continue' })).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})
