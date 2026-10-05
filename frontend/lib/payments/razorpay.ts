const RAZORPAY_SCRIPT_URL = 'https://checkout.razorpay.com/v1/checkout.js'

export interface RazorpayResponse {
  razorpay_payment_id: string
  razorpay_order_id: string
  razorpay_signature: string
}

export interface RazorpayPrefill {
  name?: string
  email?: string
  contact?: string
}

export interface RazorpayOptions {
  key: string
  amount: number
  currency: string
  name: string
  description?: string
  order_id: string
  prefill?: RazorpayPrefill
  theme?: { color?: string }
  handler?: (response: RazorpayResponse) => void
  modal?: {
    ondismiss?: () => void
  }
}

export interface RazorpayInstance {
  open(): void
  close(): void
}

export type RazorpayConstructor = new (
  options: RazorpayOptions
) => RazorpayInstance

declare global {
  interface Window {
    Razorpay?: RazorpayConstructor
  }
}

let scriptPromise: Promise<void> | null = null

export function loadRazorpay(): Promise<void> {
  if (scriptPromise) {
    return scriptPromise
  }

  scriptPromise = new Promise((resolve, reject) => {
    if (typeof window === 'undefined' || window.Razorpay) {
      resolve()
      return
    }

    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${RAZORPAY_SCRIPT_URL}"]`
    )
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => {
        scriptPromise = null
        reject(new Error('Failed to load the payment gateway.'))
      })
      resolve()
      return
    }

    const script = document.createElement('script')
    script.src = RAZORPAY_SCRIPT_URL
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => {
      scriptPromise = null
      reject(new Error('Failed to load the payment gateway.'))
    }
    document.body.appendChild(script)
  })

  return scriptPromise
}

export async function openRazorpay(
  options: RazorpayOptions
): Promise<RazorpayInstance> {
  await loadRazorpay()
  const Constructor = window.Razorpay
  if (!Constructor) {
    throw new Error('The payment gateway is unavailable. Please retry.')
  }
  return new Constructor(options)
}
