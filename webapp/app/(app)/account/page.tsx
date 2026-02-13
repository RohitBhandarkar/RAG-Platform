"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  getStoredReports,
  downloadReportPdf,
  type StoredReport,
} from "@/lib/storage";

export default function AccountPage() {
  const [reports, setReports] = useState<StoredReport[]>([]);

  useEffect(() => {
    setReports(getStoredReports());
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">
          Account
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Download previous RAG report outputs. Reports are stored in this browser.
        </p>
      </div>

      {reports.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center dark:border-slate-700 dark:bg-slate-900">
          <p className="text-slate-500 dark:text-slate-400">
            No reports saved yet. Generate a report from the{" "}
            <Link href="/rag" className="text-primary-600 hover:underline dark:text-primary-400">
              RAG Report
            </Link>{" "}
            page to see them here.
          </p>
        </div>
      ) : (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <ul className="divide-y divide-slate-200 dark:divide-slate-700">
            {reports.map((r) => (
              <li
                key={r.report_id}
                className="flex flex-wrap items-center justify-between gap-3 px-6 py-4"
              >
                <div>
                  <p className="font-medium text-slate-800 dark:text-slate-100">
                    {r.title ?? r.report_id.slice(0, 8)}
                  </p>
                  <p className="font-mono text-xs text-slate-500 dark:text-slate-400">
                    {r.report_id}
                  </p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {new Date(r.timestamp).toLocaleString()}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => downloadReportPdf(r)}
                    disabled={!r.pdf_base64}
                    className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
                  >
                    Download PDF
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
