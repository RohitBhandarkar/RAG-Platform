import { NextRequest, NextResponse } from "next/server";

/**
 * Proxy to the HTTP backend to avoid mixed content when the app is served over HTTPS (e.g. Vercel).
 * Only allows proxying to HTTP URLs with IPv4 or localhost (SSRF protection).
 */
function isAllowedBackendUrl(url: string): boolean {
  try {
    const u = new URL(url);
    if (u.protocol !== "http:") return false;
    const host = u.hostname.toLowerCase();
    if (host === "localhost" || host === "127.0.0.1") return true;
    const ipv4 = /^(\d{1,3}\.){3}\d{1,3}$/;
    if (ipv4.test(host)) {
      const parts = host.split(".").map(Number);
      return parts.every((p) => p >= 0 && p <= 255);
    }
    return false;
  } catch {
    return false;
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { baseUrl, path, method = "GET", body: reqBody } = body as {
      baseUrl?: string;
      path?: string;
      method?: string;
      body?: string;
    };
    if (!baseUrl || typeof baseUrl !== "string" || !path || typeof path !== "string") {
      return NextResponse.json(
        { error: "baseUrl and path are required" },
        { status: 400 }
      );
    }
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    const targetUrl = `${baseUrl.replace(/\/$/, "")}${normalizedPath}`;
    if (!isAllowedBackendUrl(targetUrl)) {
      return NextResponse.json(
        { error: "Proxy only allows http to IPv4 or localhost" },
        { status: 403 }
      );
    }
    const res = await fetch(targetUrl, {
      method: method || "GET",
      headers: {
        "Content-Type": "application/json",
      },
      body: method !== "GET" && reqBody != null ? reqBody : undefined,
    });
    const text = await res.text();
    try {
      const json = JSON.parse(text);
      return NextResponse.json(json, { status: res.status });
    } catch {
      return new NextResponse(text, {
        status: res.status,
        headers: { "Content-Type": res.headers.get("Content-Type") || "text/plain" },
      });
    }
  } catch (e) {
    console.error("backend-proxy error:", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Proxy failed" },
      { status: 500 }
    );
  }
}
