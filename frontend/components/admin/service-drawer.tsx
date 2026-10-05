'use client'

import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'

import { Price } from '@/components/shared/price'
import { Button } from '@/components/ui/button'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'

import {
  useCreateService,
  useUpdateService,
  type AdminServiceInput,
} from '@/features/admin/api'
import type { AdminService } from '@/features/admin/schema'

const serviceFormSchema = z.object({
  name: z.string().min(2, 'Enter a service name'),
  description: z.string().optional(),
  duration_minutes: z.coerce.number().int().min(5, 'At least 5 minutes'),
  price: z.coerce.number().int().min(0, 'Enter a valid price'),
  is_active: z.boolean(),
})

type ServiceForm = z.infer<typeof serviceFormSchema>

export function ServiceDrawer({
  service,
  open,
  onOpenChange,
}: {
  service: AdminService | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const create = useCreateService()
  const update = useUpdateService()
  const [showPriceWarning, setShowPriceWarning] = useState(false)

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<ServiceForm>({
    resolver: zodResolver(serviceFormSchema),
    defaultValues: {
      name: '',
      description: '',
      duration_minutes: 30,
      price: 0,
      is_active: true,
    },
  })

  useEffect(() => {
    if (open) {
      reset({
        name: service?.name ?? '',
        description: service?.description ?? '',
        duration_minutes: service?.duration_minutes ?? 30,
        price: service?.price ?? 0,
        is_active: service?.is_active ?? true,
      })
      setShowPriceWarning(false)
    }
  }, [open, service, reset])

  const priceValue = watch('price')
  const priceChanged =
    Boolean(service) &&
    service?.price !== undefined &&
    priceValue !== service.price

  const onSubmit = (values: ServiceForm) => {
    const body: AdminServiceInput = {
      name: values.name,
      description: values.description,
      duration_minutes: values.duration_minutes,
      price: values.price,
      is_active: values.is_active,
    }

    const options = {
      onSuccess: () => {
        toast.success(service ? 'Service updated' : 'Service created')
        onOpenChange(false)
      },
      onError: () => toast.error('Could not save the service'),
    }

    if (service) {
      update.mutate({ id: service.id, body }, options)
    } else {
      create.mutate(body, options)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-6 sm:max-w-md"
      >
        <SheetHeader>
          <SheetTitle>{service ? 'Edit service' : 'New service'}</SheetTitle>
          <SheetDescription>
            Services appear on the public booking page.
          </SheetDescription>
        </SheetHeader>

        <form
          onSubmit={handleSubmit(onSubmit)}
          noValidate
          className="flex flex-1 flex-col gap-4 overflow-y-auto"
        >
          <Field>
            <FieldLabel htmlFor="service-name">Name</FieldLabel>
            <FieldContent>
              <Input
                id="service-name"
                placeholder="Consultation"
                {...register('name')}
              />
              <FieldError
                errors={errors.name ? [{ message: errors.name.message }] : []}
              />
            </FieldContent>
          </Field>

          <Field>
            <FieldLabel htmlFor="service-description">Description</FieldLabel>
            <FieldContent>
              <Textarea
                id="service-description"
                placeholder="What this consultation covers"
                {...register('description')}
              />
            </FieldContent>
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field>
              <FieldLabel htmlFor="service-duration">Duration (min)</FieldLabel>
              <FieldContent>
                <Input
                  id="service-duration"
                  type="number"
                  min={5}
                  step={5}
                  {...register('duration_minutes')}
                />
                <FieldError
                  errors={
                    errors.duration_minutes
                      ? [{ message: errors.duration_minutes.message }]
                      : []
                  }
                />
              </FieldContent>
            </Field>

            <Field>
              <FieldLabel htmlFor="service-price">Price</FieldLabel>
              <FieldContent>
                <Input
                  id="service-price"
                  type="number"
                  min={0}
                  step={50}
                  {...register('price')}
                />
                <FieldError
                  errors={
                    errors.price ? [{ message: errors.price.message }] : []
                  }
                />
              </FieldContent>
            </Field>
          </div>

          {priceChanged && service?.price !== undefined ? (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200">
              <p className="font-medium">Price change</p>
              <p className="mt-0.5">
                Changing{' '}
                <Price amount={service.price} className="font-medium" /> to{' '}
                <Price amount={priceValue ?? 0} className="font-medium" /> only
                affects new bookings. Existing appointments keep their agreed
                price.
              </p>
              <label className="mt-2 flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={showPriceWarning}
                  onChange={(e) => setShowPriceWarning(e.target.checked)}
                />
                I understand
              </label>
            </div>
          ) : null}

          <Field orientation="horizontal">
            <FieldContent>
              <FieldLabel htmlFor="service-active">Active</FieldLabel>
              <FieldDescription>
                Inactive services are hidden from the booking page.
              </FieldDescription>
            </FieldContent>
            <Switch
              id="service-active"
              checked={watch('is_active')}
              onCheckedChange={(checked) =>
                reset({ ...watch(), is_active: checked })
              }
            />
          </Field>

          <SheetFooter className="mt-auto">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Close
            </Button>
            <Button
              type="submit"
              disabled={
                create.isPending ||
                update.isPending ||
                (priceChanged && !showPriceWarning)
              }
            >
              {create.isPending || update.isPending
                ? 'Saving…'
                : service
                  ? 'Save changes'
                  : 'Create service'}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  )
}
