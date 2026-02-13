"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  postRAGQuery,
  BackendUnreachableError,
  type RAGContextRequest,
} from "@/lib/api";
import { saveReport } from "@/lib/storage";

const defaultForm: RAGContextRequest = {
  molecular_weight: 400,
  bcs_class: "II",
  melting_point_tm: undefined,
  glass_transition_tg: undefined,
  log_p: undefined,
  target_dose: undefined,
  target_dose_unit: "mg",
  lipid_solubility: undefined,
  lipid_solubility_unit: "mg/g",
  k: 5,
};

export default function RAGPage() {
  const [form, setForm] = useState<RAGContextRequest>(defaultForm);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    report_id: string;
    markdown: string;
    pdf_base64: string;
  } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const data = await postRAGQuery(form);
      setResult({
        report_id: data.report_id,
        markdown: data.markdown,
        pdf_base64: data.pdf_base64,
      });
      saveReport({
        report_id: data.report_id,
        timestamp: new Date().toISOString(),
        markdown: data.markdown,
        pdf_base64: data.pdf_base64,
        title: `BCS ${form.bcs_class} / MW ${form.molecular_weight}`,
      });
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

  const downloadPdf = () => {
    if (!result?.pdf_base64) return;
    try {
      const bin = atob(result.pdf_base64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const blob = new Blob([bytes], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `formulation_report_${result.report_id.slice(0, 8)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError("Failed to download PDF");
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">
          RAG Report
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Enter API properties to generate a formulation experiment report. Use the Report ID when submitting in-house experiment results.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            API properties
          </h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <label className="block">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">BCS class</span>
              <select
                value={form.bcs_class}
                onChange={(e) => setForm({ ...form, bcs_class: e.target.value })}
                className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              >
                <option value="I">I</option>
                <option value="II">II</option>
                <option value="III">III</option>
                <option value="IV">IV</option>
              </select>
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Molecular weight (Da)</span>
              <input
                type="number"
                step="any"
                required
                value={form.molecular_weight}
                onChange={(e) =>
                  setForm({ ...form, molecular_weight: parseFloat(e.target.value) || 0 })
                }
                className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Melting point Tm (°C)</span>
              <input
                type="number"
                step="any"
                value={form.melting_point_tm ?? ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    melting_point_tm: e.target.value ? parseFloat(e.target.value) : undefined,
                  })
                }
                className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                placeholder="Optional"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Glass transition Tg (°C)</span>
              <input
                type="number"
                step="any"
                value={form.glass_transition_tg ?? ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    glass_transition_tg: e.target.value ? parseFloat(e.target.value) : undefined,
                  })
                }
                className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                placeholder="Optional"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">LogP</span>
              <input
                type="number"
                step="any"
                value={form.log_p ?? ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    log_p: e.target.value ? parseFloat(e.target.value) : undefined,
                  })
                }
                className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                placeholder="Optional"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Target dose</span>
              <div className="mt-1 flex gap-2">
                <input
                  type="number"
                  step="any"
                  min={0}
                  value={form.target_dose ?? ""}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      target_dose: e.target.value ? parseFloat(e.target.value) : undefined,
                    })
                  }
                  className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                  placeholder="Optional"
                />
                <input
                  type="text"
                  value={form.target_dose_unit}
                  onChange={(e) =>
                    setForm({ ...form, target_dose_unit: e.target.value })
                  }
                  className="w-20 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                />
              </div>
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Lipid solubility</span>
              <div className="mt-1 flex gap-2">
                <input
                  type="number"
                  step="any"
                  min={0}
                  value={form.lipid_solubility ?? ""}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      lipid_solubility: e.target.value ? parseFloat(e.target.value) : undefined,
                    })
                  }
                  className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                  placeholder="Optional"
                />
                <input
                  type="text"
                  value={form.lipid_solubility_unit}
                  onChange={(e) =>
                    setForm({ ...form, lipid_solubility_unit: e.target.value })
                  }
                  className="w-24 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                />
              </div>
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">k (nearest results)</span>
              <input
                type="number"
                min={1}
                max={20}
                value={form.k ?? 5}
                onChange={(e) =>
                  setForm({ ...form, k: parseInt(e.target.value, 10) || 5 })
                }
                className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </label>
          </div>
          <div className="mt-6 flex gap-3">
            <button
              type="submit"
              disabled={loading}
              className="rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
            >
              {loading ? "Generating…" : "Generate report"}
            </button>
          </div>
        </div>
      </form>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-950/30 dark:text-red-200">
          {error}
        </div>
      )}

      {result && (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <div className="border-b border-slate-200 px-6 py-4 dark:border-slate-700">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Report ID</p>
                <p className="font-mono text-sm text-slate-800 dark:text-slate-100">
                  {result.report_id}
                </p>
              </div>
              <button
                type="button"
                onClick={downloadPdf}
                className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
              >
                Download PDF
              </button>
            </div>
          </div>
          <div className="max-h-[60vh] overflow-y-auto p-6">
            <div className="report-markdown max-w-none">
              <ReactMarkdown>{result.markdown}</ReactMarkdown>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
