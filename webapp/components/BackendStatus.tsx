"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { getHealth, getApiBaseUrl, BackendUnreachableError } from "@/lib/api";

const POLL_INTERVAL_MS = 8000;

export default function BackendStatus() {
  const [status, setStatus] = useState<"checking" | "up" | "down">("checking");
  const [message, setMessage] = useState<string>("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const check = useCallback(() => {
    setStatus("checking");
    getHealth()
      .then(() => {
        setStatus("up");
        setMessage(getApiBaseUrl());
      })
      .catch((e) => {
        setStatus("down");
        setMessage(e instanceof BackendUnreachableError ? e.message : "Backend unavailable");
      });
  }, []);

  useEffect(() => {
    check();
    const onUpdate = () => check();
    window.addEventListener("backendUrlUpdated", onUpdate);
    return () => window.removeEventListener("backendUrlUpdated", onUpdate);
  }, [check]);

  // When down, poll so status updates when backend comes back without refresh
  useEffect(() => {
    if (status !== "down") {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    pollRef.current = setInterval(check, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [status, check]);

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span
        className={`inline-block h-2.5 w-2.5 rounded-full shrink-0 ${
          status === "up"
            ? "bg-emerald-500"
            : status === "down"
            ? "bg-red-500"
            : "animate-pulse bg-amber-500"
        }`}
        title={status === "up" ? "Backend reachable" : status === "down" ? message : "Checking…"}
      />
      <span className="text-xs text-slate-500 dark:text-slate-400">
        {status === "up" && "Backend connected"}
        {status === "down" && message}
        {status === "checking" && "Checking backend…"}
      </span>
      {status === "down" && (
        <button
          type="button"
          onClick={() => check()}
          className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
        >
          Retry
        </button>
      )}
    </div>
  );
}
