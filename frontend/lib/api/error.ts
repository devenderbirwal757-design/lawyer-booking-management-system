export const ErrorCodes = {
  invalidToken: 'INVALID_TOKEN',
  expiredHold: 'EXPIRED_HOLD',
  slotUnavailable: 'SLOT_UNAVAILABLE',
  slotOccupied: 'SLOT_OCCUPIED',
  orderInvalid: 'ORDER_INVALID',
  notFound: 'NOT_FOUND',
  validation: 'VALIDATION_ERROR',
  rateLimited: 'RATE_LIMITED',
  internal: 'INTERNAL_ERROR',
} as const

export type ErrorCode = (typeof ErrorCodes)[keyof typeof ErrorCodes]

export interface ApiErrorDetails {
  [key: string]: unknown
}

interface ApiErrorBody {
  error: {
    code: ErrorCode | string
    message: string
    details?: ApiErrorDetails
  }
}

export class ApiError extends Error {
  readonly code: ErrorCode | string
  readonly details: ApiErrorDetails | undefined
  readonly status: number

  constructor(
    status: number,
    code: ErrorCode | string,
    message: string,
    details?: ApiErrorDetails
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }

  get isSlotUnavailable() {
    return this.code === ErrorCodes.slotUnavailable
  }

  get isExpiredHold() {
    return this.code === ErrorCodes.expiredHold
  }

  get isInvalidToken() {
    return this.code === ErrorCodes.invalidToken
  }
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error
  }

  if (error instanceof Error) {
    return new ApiError(0, ErrorCodes.internal, error.message)
  }

  return new ApiError(0, ErrorCodes.internal, 'An unknown error occurred')
}

export function parseApiErrorBody(
  status: number,
  body: unknown
): ApiError | null {
  if (!body || typeof body !== 'object') {
    return null
  }

  const candidate = body as ApiErrorBody
  if (!candidate.error || typeof candidate.error.message !== 'string') {
    return null
  }

  return new ApiError(
    status,
    candidate.error.code ?? ErrorCodes.internal,
    candidate.error.message,
    candidate.error.details
  )
}
