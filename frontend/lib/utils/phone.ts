import { z } from 'zod'

export const indianPhoneSchema = z
  .string()
  .trim()
  .regex(/^[6-9]\d{9}$/, 'Enter a valid 10-digit mobile number')

export type IndianPhone = z.infer<typeof indianPhoneSchema>

export function toE164(phone: string): string {
  const normalized = indianPhoneSchema.parse(phone)
  return `+91${normalized}`
}

export function stripLeading0(phone: string): string {
  return phone.replace(/^0+/, '')
}
