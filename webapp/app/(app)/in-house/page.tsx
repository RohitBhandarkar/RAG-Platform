"use client";

import { useState } from "react";
import {
  postInternalExperiment,
  getInternalExperimentsByReport,
  BackendUnreachableError,
  type InternalExperimentResult,
} from "@/lib/api";

export default function InHousePage() {
  const [reportId, setReportId] = useState("");
  const [experimentSummary, setExperimentSummary] = useState("");
  const [notes, setNotes] = useState("");
  const [outcome, setOutcome] = useState("");
  const [conductedAt, setConductedAt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [entries, setEntries] = useState<InternalExperimentResult[]>([]);
  const [loadingEntries, setLoadingEntries] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (!reportId.trim() || !experimentSummary.trim()) {
      setError("Report ID and experiment summary are required.");
      return;
    }
    setLoading(true);
    try {
      await postInternalExperiment({
        report_id: reportId.trim(),
        experiment_summary: experimentSummary.trim(),
        notes: notes.trim() || undefined,
        outcome: outcome.trim() || undefined,
        conducted_at: conductedAt.trim() || undefined,
      });
      setSuccess("In-house experiment saved and embedding created. It will appear in future RAG reports when relevant.");
      setExperimentSummary("");
      setNotes("");
      setOutcome("");
      setConductedAt("");
      if (reportId) fetchEntries(reportId.trim());
    } catch (e) {
      setError(
        e instanceof BackendUnreachableError
          ? e.message
          : e instanceof Error
          ? e.message
          : "Request failed"
      );
    } finally {
      setLoading(false);
    }
  };

  const fetchEntries = async (id: string) => {
    if (!id) return;
    setLoadingEntries(true);
    setError(null);
    try {
      const list = await getInternalExperimentsByReport(id);
      setEntries(list);
    } catch (e) {
      setEntries([]);
      if (e instanceof BackendUnreachableError) setError(e.message);
    } finally {
      setLoadingEntries(false);
    }
  };

  const handleLookup = (e: React.FormEvent) => {
    e.preventDefault();
    if (reportId.trim()) fetchEntries(reportId.trim());
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">
          In-house experimentation
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Submit lab results for a report. Use the Report ID from the generated report. You can submit multiple entries per report.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            New in-house result
          </h2>
          <div className="mt-4 space-y-4">
            <label className="block">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Report ID</span>
              <input
                type="text"
                required
                value={reportId}
                onChange={(e) => setReportId(e.target.value)}
                placeholder="e.g. f36e0ce8-a455-457c-9f88-6e1617a170d0"
                className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-mono dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Experiment summary *</span>
              <textarea
                required
                rows={3}
                value={experimentSummary}
                onChange={(e) => setExperimentSummary(e.target.value)}
                className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                placeholder="Brief summary of the experiment and findings..."
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Notes</span>
              <textarea
                rows={2}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                placeholder="Optional"
              />
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Outcome</span>
                <select
                  value={outcome}
                  onChange={(e) => setOutcome(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                >
                  <option value="">—</option>
                  <option value="success">Success</option>
                  <option value="failed">Failed</option>
                  <option value="partial">Partial</option>
                </select>
              </label>
              <label className="block">
                <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Conducted (YYYY-MM-DD)</span>
                <input
                  type="date"
                  value={conductedAt}
                  onChange={(e) => setConductedAt(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                />
              </label>
            </div>
          </div>
          <div className="mt-6 flex gap-3">
            <button
              type="submit"
              disabled={loading}
              className="rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
            >
              {loading ? "Submitting…" : "Submit"}
            </button>
          </div>
        </div>
      </form>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-950/30 dark:text-red-200">
          {error}
        </div>
      )}
      {success && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200">
          {success}
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
          View entries for a report
        </h2>
        <form onSubmit={handleLookup} className="mt-4 flex gap-2">
          <input
            type="text"
            value={reportId}
            onChange={(e) => setReportId(e.target.value)}
            placeholder="Report ID"
            className="flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-mono dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          />
          <button
            type="submit"
            disabled={loadingEntries}
            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            {loadingEntries ? "Loading…" : "Look up"}
          </button>
        </form>
        {entries.length > 0 && (
          <ul className="mt-4 divide-y divide-slate-200 dark:divide-slate-700">
            {entries.map((entry) => (
              <li key={entry.id} className="py-3">
                <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                  {entry.experiment_summary}
                </p>
                {entry.notes && (
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{entry.notes}</p>
                )}
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  Outcome: {entry.outcome ?? "—"} · Conducted: {entry.conducted_at ?? "—"}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
