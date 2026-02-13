"use client";

import { useRouter } from "next/navigation";
import { SignOutButton } from "@clerk/nextjs";

export default function RestrictedPage() {
  const router = useRouter();

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-4">
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-center dark:border-amber-800 dark:bg-amber-950/30 max-w-md">
        <h1 className="text-lg font-semibold text-amber-800 dark:text-amber-200">
          Access restricted
        </h1>
        <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">
          This application is currently limited to a single account. Your account is not on the allowlist.
        </p>
        <div className="mt-4 flex justify-center gap-2">
          <SignOutButton signOutCallback={() => router.push("/sign-in")}>
            <button className="rounded-md bg-slate-200 px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-300 dark:bg-slate-700 dark:text-slate-200 dark:hover:bg-slate-600">
              Sign out
            </button>
          </SignOutButton>
        </div>
      </div>
    </div>
  );
}
