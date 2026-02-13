/**
 * Single-account allowlist: only the email in NEXT_PUBLIC_ALLOWED_CLERK_EMAIL can use the app.
 * Compare with Clerk user.primaryEmailAddress.emailAddress (or primaryEmailAddress?.emailAddress).
 */

export function getAllowedEmail(): string | null {
  if (typeof window === "undefined") {
    return process.env.NEXT_PUBLIC_ALLOWED_CLERK_EMAIL ?? null;
  }
  return process.env.NEXT_PUBLIC_ALLOWED_CLERK_EMAIL ?? null;
}

export function isAllowedUser(email: string | undefined | null): boolean {
  const allowed = getAllowedEmail();
  if (!allowed) return true; // no allowlist => allow all (for dev)
  if (!email) return false;
  return email.trim().toLowerCase() === allowed.trim().toLowerCase();
}
