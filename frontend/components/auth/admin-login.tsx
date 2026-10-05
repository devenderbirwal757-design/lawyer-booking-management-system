'use client'

import { zodResolver } from '@hookform/resolvers/zod'
import { useSearchParams } from 'next/navigation'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import {
  Field,
  FieldContent,
  FieldError,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { ApiError, ErrorCodes } from '@/lib/api/error'

import { loginAdmin } from '@/features/auth/api'
import { adminLoginSchema, type AdminLogin } from '@/features/auth/schema'

function safeNextPath(searchParams: URLSearchParams): string {
  const next = searchParams.get('next') ?? '/admin/dashboard'
  return next.startsWith('/') && !next.startsWith('//')
    ? next
    : '/admin/dashboard'
}

function loginErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return 'Something went wrong. Please try again.'
  }
  if (error.code === ErrorCodes.rateLimited) {
    return 'Too many login attempts. Please wait a few minutes and try again.'
  }
  if (error.status === 401) {
    return 'Invalid email or password.'
  }
  return error.message
}

export function AdminLogin() {
  const searchParams = useSearchParams()
  const [formError, setFormError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<AdminLogin>({
    resolver: zodResolver(adminLoginSchema),
  })

  const onSubmit = handleSubmit(async (credentials) => {
    setFormError(null)
    try {
      await loginAdmin(credentials)
      window.location.assign(safeNextPath(searchParams))
    } catch (error) {
      setFormError(loginErrorMessage(error))
    }
  })

  return (
    <div className="mx-auto w-full max-w-sm px-4 py-16">
      <div className="flex flex-col gap-2 text-center">
        <h1 className="font-serif text-3xl tracking-tight">Admin login</h1>
        <p className="text-sm text-muted-foreground">
          Sign in with your admin credentials.
        </p>
      </div>

      {formError && (
        <p
          role="alert"
          className="mt-6 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
        >
          {formError}
        </p>
      )}

      <form onSubmit={onSubmit} className="mt-8 flex flex-col gap-5" noValidate>
        <Field>
          <FieldLabel htmlFor="email">Email</FieldLabel>
          <FieldContent>
            <Input
              id="email"
              type="email"
              autoComplete="username"
              placeholder="you@chambers.in"
              disabled={isSubmitting}
              {...register('email')}
            />
            <FieldError
              errors={errors.email ? [{ message: errors.email.message }] : []}
            />
          </FieldContent>
        </Field>

        <Field>
          <FieldLabel htmlFor="password">Password</FieldLabel>
          <FieldContent>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              disabled={isSubmitting}
              {...register('password')}
            />
            <FieldError
              errors={
                errors.password ? [{ message: errors.password.message }] : []
              }
            />
          </FieldContent>
        </Field>

        <Button type="submit" size="lg" disabled={isSubmitting}>
          {isSubmitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </div>
  )
}
