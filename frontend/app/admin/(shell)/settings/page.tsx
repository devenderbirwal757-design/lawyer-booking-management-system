'use client'

import { PlusIcon, Trash2Icon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/shared/page-header'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { toApiError } from '@/lib/api/error'

import {
  useAdminSettings,
  useAvailabilityExceptions,
  useAvailabilityRules,
  useCreateAvailabilityException,
  useCreateAvailabilityRule,
  useDeleteAvailabilityException,
  useDeleteAvailabilityRule,
  useUpdateAdminSettings,
} from '@/features/admin/api'
import type { AdminSettings } from '@/features/admin/schema'

const WEEKDAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

const CURRENCIES = ['INR', 'USD', 'GBP', 'EUR', 'AED']

export default function AdminSettingsPage() {
  const settings = useAdminSettings()
  const update = useUpdateAdminSettings()

  const [form, setForm] = useState<AdminSettings | null>(null)

  useEffect(() => {
    if (settings.data) {
      setForm(settings.data)
    }
  }, [settings.data])

  const patch = (values: Partial<AdminSettings>) =>
    setForm((current) => (current ? { ...current, ...values } : current))

  const save = () => {
    if (!form) return
    update.mutate(
      {
        business_name: form.business_name,
        email: form.email,
        phone: form.phone,
        address: form.address ?? '',
        about: form.about ?? '',
        timezone: form.timezone,
        currency: form.currency,
        faq: form.faq,
        reminder_offsets: form.reminder_offsets,
        cancellation_policy: form.cancellation_policy,
      },
      {
        onSuccess: () => toast.success('Settings saved'),
        onError: (error) => toast.error(toApiError(error).message),
      }
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Practice profile, booking policy, and working hours."
        actions={
          <Button onClick={save} disabled={!form || update.isPending}>
            {update.isPending ? 'Saving…' : 'Save settings'}
          </Button>
        }
      />

      {!form ? (
        <p className="text-sm text-muted-foreground">Loading settings…</p>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Practice profile</CardTitle>
              <CardDescription>
                Shown on the public site and used on receipts.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <Field label="Business name">
                <Input
                  value={form.business_name}
                  onChange={(e) => patch({ business_name: e.target.value })}
                />
              </Field>
              <Field label="Email">
                <Input
                  type="email"
                  value={form.email ?? ''}
                  onChange={(e) => patch({ email: e.target.value })}
                />
              </Field>
              <Field label="Phone">
                <Input
                  value={form.phone ?? ''}
                  onChange={(e) => patch({ phone: e.target.value })}
                />
              </Field>
              <Field label="Address">
                <Input
                  value={form.address ?? ''}
                  onChange={(e) => patch({ address: e.target.value })}
                />
              </Field>
              <div className="sm:col-span-2">
                <Field label="About">
                  <Textarea
                    value={form.about ?? ''}
                    onChange={(e) => patch({ about: e.target.value })}
                    className="min-h-24"
                  />
                </Field>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Locale</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <Field label="Currency">
                <Select
                  value={form.currency}
                  onValueChange={(value) => patch({ currency: value })}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CURRENCIES.map((currency) => (
                      <SelectItem key={currency} value={currency}>
                        {currency}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Timezone">
                <Input
                  value={form.timezone}
                  onChange={(e) => patch({ timezone: e.target.value })}
                />
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">FAQ</CardTitle>
              <CardDescription>
                Questions shown on the public booking page.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              {form.faq.map((item, index) => (
                <div key={index} className="flex flex-col gap-2">
                  <div className="flex gap-2">
                    <Input
                      value={item.question}
                      placeholder="Question"
                      onChange={(e) => {
                        const faq = [...form.faq]
                        faq[index] = { ...item, question: e.target.value }
                        patch({ faq })
                      }}
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Remove question"
                      onClick={() =>
                        patch({
                          faq: form.faq.filter((_, i) => i !== index),
                        })
                      }
                    >
                      <Trash2Icon className="size-4" />
                    </Button>
                  </div>
                  <Textarea
                    value={item.answer}
                    placeholder="Answer"
                    onChange={(e) => {
                      const faq = [...form.faq]
                      faq[index] = { ...item, answer: e.target.value }
                      patch({ faq })
                    }}
                  />
                </div>
              ))}
              <Button
                variant="outline"
                size="sm"
                className="w-fit"
                onClick={() =>
                  patch({ faq: [...form.faq, { question: '', answer: '' }] })
                }
              >
                <PlusIcon className="size-4" /> Add question
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">
                Reminders &amp; cancellations
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-3">
              <Field label="Reminder offsets (hours before)">
                <Input
                  value={form.reminder_offsets.join(', ')}
                  placeholder="24, 2"
                  onChange={(e) =>
                    patch({
                      reminder_offsets: e.target.value
                        .split(',')
                        .map((value) => Number(value.trim()))
                        .filter((value) => Number.isFinite(value) && value > 0),
                    })
                  }
                />
              </Field>
              <Field label="Free-cancel window (hours)">
                <Input
                  type="number"
                  min={0}
                  value={form.cancellation_policy?.window_hours ?? 0}
                  onChange={(e) =>
                    patch({
                      cancellation_policy: {
                        ...form.cancellation_policy,
                        window_hours: Number(e.target.value),
                      },
                    })
                  }
                />
              </Field>
              <Field label="Refund percent inside window">
                <Input
                  type="number"
                  min={0}
                  max={100}
                  value={form.cancellation_policy?.refund_percent ?? 100}
                  onChange={(e) =>
                    patch({
                      cancellation_policy: {
                        ...form.cancellation_policy,
                        refund_percent: Number(e.target.value),
                      },
                    })
                  }
                />
              </Field>
            </CardContent>
          </Card>
        </>
      )}

      <WorkingHoursCard />
      <ExceptionsCard />
    </div>
  )
}

function WorkingHoursCard() {
  const rules = useAvailabilityRules()
  const create = useCreateAvailabilityRule()
  const remove = useDeleteAvailabilityRule()

  const [weekday, setWeekday] = useState('0')
  const [start, setStart] = useState('10:00')
  const [end, setEnd] = useState('18:00')

  const add = () => {
    create.mutate(
      { weekday: Number(weekday), start_time: start, end_time: end },
      {
        onSuccess: () => toast.success('Working hours added'),
        onError: (error) => toast.error(toApiError(error).message),
      }
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Working hours</CardTitle>
        <CardDescription>
          Recurring availability that clients can book against.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul className="flex flex-col gap-2 text-sm">
          {(rules.data ?? []).map((rule) => (
            <li
              key={rule.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2"
            >
              <span>
                <span className="font-medium">
                  {WEEKDAYS[rule.weekday ?? 0] ?? 'Day'}
                </span>
                <span className="ml-2 text-muted-foreground">
                  {rule.start_time} – {rule.end_time}
                </span>
              </span>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Remove working hours"
                onClick={() => remove.mutate(rule.id)}
              >
                <Trash2Icon className="size-4" />
              </Button>
            </li>
          ))}
          {rules.isLoading ? (
            <li className="text-muted-foreground">Loading…</li>
          ) : null}
        </ul>

        <div className="flex flex-wrap items-end gap-2">
          <Select value={weekday} onValueChange={setWeekday}>
            <SelectTrigger className="h-9 w-36" aria-label="Weekday">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {WEEKDAYS.map((label, index) => (
                <SelectItem key={label} value={String(index)}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            type="time"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="h-9 w-32"
            aria-label="Start time"
          />
          <Input
            type="time"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="h-9 w-32"
            aria-label="End time"
          />
          <Button onClick={add} disabled={create.isPending}>
            <PlusIcon className="size-4" /> Add
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function ExceptionsCard() {
  const exceptions = useAvailabilityExceptions()
  const create = useCreateAvailabilityException()
  const remove = useDeleteAvailabilityException()

  const [date, setDate] = useState('')
  const [note, setNote] = useState('')

  const add = () => {
    if (!date) return
    create.mutate(
      { date, note: note || undefined },
      {
        onSuccess: () => {
          setDate('')
          setNote('')
          toast.success('Exception added')
        },
        onError: (error) => toast.error(toApiError(error).message),
      }
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Availability exceptions</CardTitle>
        <CardDescription>One-off closures or changed hours.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul className="flex flex-col gap-2 text-sm">
          {(exceptions.data ?? []).map((exception) => (
            <li
              key={exception.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2"
            >
              <span>
                <span className="font-medium">{exception.date}</span>
                {exception.note ? (
                  <span className="ml-2 text-muted-foreground">
                    {exception.note}
                  </span>
                ) : null}
              </span>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Remove exception"
                onClick={() => remove.mutate(exception.id)}
              >
                <Trash2Icon className="size-4" />
              </Button>
            </li>
          ))}
          {exceptions.isLoading ? (
            <li className="text-muted-foreground">Loading…</li>
          ) : null}
        </ul>

        <div className="flex flex-wrap items-end gap-2">
          <Input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="h-9 w-40"
            aria-label="Exception date"
          />
          <Input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (optional)"
            className="h-9 w-56"
            aria-label="Exception note"
          />
          <Button onClick={add} disabled={!date || create.isPending}>
            <PlusIcon className="size-4" /> Add exception
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  )
}
