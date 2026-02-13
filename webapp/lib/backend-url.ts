/**
 * User-configured backend API URL (set after login). Stored in localStorage
 * as full URL; UI only asks for VM IP (and optional port), we add scheme and default port.
 */

const STORAGE_KEY = "rag_api_url";

/** Default port for the FastAPI backend on the VM. */
export const DEFAULT_BACKEND_PORT = 8080;

export function getStoredApiUrl(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const u = localStorage.getItem(STORAGE_KEY);
    return u && u.trim() ? u.trim().replace(/\/$/, "") : null;
  } catch {
    return null;
  }
}

export function setStoredApiUrl(url: string): void {
  if (typeof window === "undefined") return;
  const value = url.trim().replace(/\/$/, "");
  localStorage.setItem(STORAGE_KEY, value || "");
  window.dispatchEvent(new CustomEvent("backendUrlUpdated"));
}

/**
 * Build full backend base URL from user input (VM IP or IP:port).
 * We always use http and default port 8080 if no port given.
 */
export function fullUrlFromIpInput(input: string): string {
  const raw = input.trim().replace(/\/$/, "");
  if (!raw) return "";
  let host = raw;
  let port = String(DEFAULT_BACKEND_PORT);
  if (raw.includes(":")) {
    const lastColon = raw.lastIndexOf(":");
    host = raw.slice(0, lastColon).trim();
    const portPart = raw.slice(lastColon + 1).trim();
    if (portPart) port = portPart;
  }
  // Strip any protocol the user might have typed
  host = host.replace(/^https?:\/\//, "").split("/")[0];
  if (!host) return "";
  return `http://${host}:${port}`;
}

/**
 * Value to show in the VM IP input from a stored full URL.
 */
export function displayValueFromStoredUrl(fullUrl: string): string {
  const u = fullUrl.trim().replace(/\/$/, "");
  if (!u) return "";
  try {
    const url = new URL(u);
    const port = url.port && url.port !== "80" && url.port !== "443" ? `:${url.port}` : "";
    return `${url.hostname}${port}`;
  } catch {
    return u.replace(/^https?:\/\//, "").split("/")[0];
  }
}
