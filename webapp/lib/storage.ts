/**
 * Client-side storage for previous RAG reports (Account page downloads).
 * Key: rag_reports. Value: array of { report_id, timestamp, markdown, pdf_base64?, title? }.
 */

const STORAGE_KEY = "rag_reports";
const MAX_ITEMS = 100;

export interface StoredReport {
  report_id: string;
  timestamp: string; // ISO
  markdown: string;
  pdf_base64?: string;
  title?: string;
}

function getStored(): StoredReport[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as StoredReport[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function setStored(items: StoredReport[]) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(-MAX_ITEMS)));
  } catch {
    // ignore
  }
}

export function saveReport(report: StoredReport): void {
  const list = getStored();
  const existing = list.findIndex((r) => r.report_id === report.report_id);
  const entry: StoredReport = {
    ...report,
    title: report.title || `Report ${report.report_id.slice(0, 8)}`,
  };
  if (existing >= 0) {
    list[existing] = entry;
  } else {
    list.push(entry);
  }
  setStored(list);
}

export function getStoredReports(): StoredReport[] {
  return getStored().sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );
}

export function downloadReportPdf(report: StoredReport): void {
  if (!report.pdf_base64) return;
  try {
    const bin = atob(report.pdf_base64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const blob = new Blob([bytes], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `formulation_report_${report.report_id.slice(0, 8)}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error(e);
  }
}
