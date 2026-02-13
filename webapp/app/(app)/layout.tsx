"use client";

import { useUser } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { isAllowedUser } from "@/lib/auth";
import Nav from "@/components/Nav";
import BackendStatus from "@/components/BackendStatus";
import BackendUrlSettings from "@/components/BackendUrlSettings";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isLoaded, isSignedIn, user } = useUser();
  const router = useRouter();

  useEffect(() => {
    if (!isLoaded) return;
    if (!isSignedIn) {
      router.replace("/sign-in");
      return;
    }
    const email = user?.primaryEmailAddress?.emailAddress ?? null;
    if (!isAllowedUser(email)) {
      router.replace("/restricted");
      return;
    }
  }, [isLoaded, isSignedIn, user, router]);

  if (!isLoaded || !isSignedIn) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-slate-500">Loading…</div>
      </div>
    );
  }

  const email = user?.primaryEmailAddress?.emailAddress ?? null;
  if (!isAllowedUser(email)) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-slate-500">Redirecting…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Nav />
      <div className="border-b border-slate-200 bg-slate-50/50 px-4 py-2 dark:border-slate-800 dark:bg-slate-900/50">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
          <div className="min-w-0 flex-1 max-w-md">
            <BackendUrlSettings />
          </div>
          <BackendStatus />
        </div>
      </div>
      <main className="flex-1 mx-auto w-full max-w-6xl px-4 py-6">{children}</main>
    </div>
  );
}
