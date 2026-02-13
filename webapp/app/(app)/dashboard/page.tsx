"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import BackendStatus from "@/components/BackendStatus";
import { getHealth } from "@/lib/api";
import { getStoredReports } from "@/lib/storage";

export default function DashboardPage() {
  const [backendUp, setBackendUp] = useState<boolean | null>(null);
  const [reportCount, setReportCount] = useState(0);

  useEffect(() => {
    getHealth()
      .then(() => setBackendUp(true))
      .catch(() => setBackendUp(false));
  }, []);

  useEffect(() => {
    setReportCount(getStoredReports().length);
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">
          Dashboard
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Overview and quick actions for the RAG Formulation Platform.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <div className="flex items-center gap-3">
            <div
              className={`flex h-10 w-10 items-center justify-center rounded-lg ${
                backendUp === true
                  ? "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/40 dark:text-emerald-400"
                  : backendUp === false
                  ? "bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400"
                  : "bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400"
              }`}
            >
              <span className="text-lg font-semibold">
                {backendUp === true ? "✓" : backendUp === false ? "✕" : "…"}
              </span>
            </div>
            <div>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
                Backend status
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {backendUp === true ? "Connected" : backendUp === false ? "Not connected" : "Checking…"}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-100 text-primary-600 dark:bg-primary-900/40 dark:text-primary-400">
              <span className="text-lg font-semibold">{reportCount}</span>
            </div>
            <div>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
                Saved reports
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Stored in this browser
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
            Quick actions
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link
              href="/rag"
              className="inline-flex items-center rounded-md bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700"
            >
              Generate report
            </Link>
            <Link
              href="/in-house"
              className="inline-flex items-center rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            >
              Submit in-house result
            </Link>
          </div>
        </div>
      </div>

      {backendUp === false && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/30">
          <p className="text-sm text-amber-800 dark:text-amber-200">
            The backend is not reachable. Set the <strong>Backend API URL</strong> in the bar above to your FastAPI server (e.g. your GCP VM URL) and ensure the VM is running. RAG and in-house experiment features will not work until the backend is available.
          </p>
        </div>
      )}
    </div>
  );
}
