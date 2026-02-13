/**
 * API client for the RAG Platform FastAPI backend.
 * When the app is served over HTTPS (e.g. Vercel) and the backend is HTTP, requests
 * go through /api/backend-proxy to avoid mixed content blocking.
 */

import { getStoredApiUrl } from "./backend-url";

function getBaseUrl(): string {
  if (typeof window !== "undefined") {
    const stored = getStoredApiUrl();
    if (stored) return stored;
  }
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (url && url.trim()) return url.trim().replace(/\/$/, "");
  return "http://localhost:8000";
}

/** True when we must use the proxy (HTTPS page calling HTTP backend). */
function useProxy(): boolean {
  if (typeof window === "undefined") return false;
  const base = getBaseUrl();
  return window.location.protocol === "https:" && base.startsWith("http://");
}

async function fetchViaProxy(path: string, options: RequestInit = {}): Promise<Response> {
  const base = getBaseUrl();
  const pathOnly = path.startsWith("/") ? path : `/${path}`;
  const method = (options.method || "GET").toUpperCase();
  const body = options.body != null
    ? (typeof options.body === "string" ? options.body : JSON.stringify(options.body))
    : undefined;
  return fetch("/api/backend-proxy", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ baseUrl: base, path: pathOnly, method, body }),
  });
}

export class BackendUnreachableError extends Error {
  constructor(message = "Backend is not available. Please ensure the GCP VM is running.") {
    super(message);
    this.name = "BackendUnreachableError";
  }
}

async function fetchApi<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const base = getBaseUrl();
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;

  if (useProxy()) {
    const res = await fetchViaProxy(path, options);
    const text = await res.text();
    if (!res.ok) throw new Error(text || `HTTP ${res.status}`);
    try {
      return JSON.parse(text) as T;
    } catch {
      throw new Error(text || "Invalid JSON");
    }
  }

  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `HTTP ${res.status}`);
    }
    return res.json() as Promise<T>;
  } catch (e) {
    if (e instanceof TypeError && e.message.includes("fetch")) {
      throw new BackendUnreachableError();
    }
    if (e instanceof Error && (e.message.includes("Failed to fetch") || e.message.includes("NetworkError"))) {
      throw new BackendUnreachableError();
    }
    throw e;
  }
}

// --- RAG ---

export interface RAGContextRequest {
  molecular_weight: number;
  bcs_class: string;
  melting_point_tm?: number;
  glass_transition_tg?: number;
  log_p?: number;
  target_dose?: number;
  target_dose_unit?: string;
  lipid_solubility?: number;
  lipid_solubility_unit?: string;
  k?: number;
}

export interface RAGQueryResponse {
  report_id: string;
  markdown: string;
  pdf_base64: string;
}

export async function postRAGQuery(body: RAGContextRequest): Promise<RAGQueryResponse> {
  return fetchApi<RAGQueryResponse>("/RAG/query", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getRAGContext(body: RAGContextRequest) {
  return fetchApi("/RAG/context", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// --- Health (for backend status) ---

export async function getHealth(): Promise<{ status: string }> {
  if (useProxy()) {
    const res = await fetchViaProxy("/health", { method: "GET" });
    const text = await res.text();
    if (!res.ok) throw new Error("Unhealthy");
    return JSON.parse(text) as { status: string };
  }
  const base = getBaseUrl();
  const res = await fetch(`${base}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error("Unhealthy");
  return res.json();
}

// --- Internal experiment results ---

export interface InternalExperimentUpdateRequest {
  report_id: string;
  experiment_summary: string;
  notes?: string;
  outcome?: string;
  conducted_at?: string;
}

export interface InternalExperimentResult {
  id: number;
  report_id: string;
  bcs_class: string;
  molecular_weight_min?: number;
  molecular_weight_max?: number;
  experiment_summary: string;
  notes?: string;
  outcome?: string;
  conducted_at?: string;
  created_at?: string;
}

export async function getInternalExperimentsByReport(reportId: string): Promise<InternalExperimentResult[]> {
  return fetchApi<InternalExperimentResult[]>(`/RAG/internal-experiment-results/${reportId}`);
}

export async function postInternalExperiment(body: InternalExperimentUpdateRequest) {
  return fetchApi("/RAG/internal-experiment-results", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getApiBaseUrl(): string {
  return getBaseUrl();
}
