/**
 * User-configured backend API URL (set after login). Stored in localStorage
 * so it persists and can be updated when the VM IP changes.
 */

const STORAGE_KEY = "rag_api_url";

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
