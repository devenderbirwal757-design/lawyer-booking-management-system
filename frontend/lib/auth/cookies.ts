export const SESSION_COOKIES = ['access_token', 'refresh_token'] as const

export function hasSessionCookies(has: (name: string) => boolean): boolean {
  return SESSION_COOKIES.some(has)
}
