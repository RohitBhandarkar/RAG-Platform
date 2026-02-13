"use client";

import { useEffect, useState } from "react";
import { getHealth, getApiBaseUrl, BackendUnreachableError } from "@/lib/api";

export default function BackendStatus() {
  const [status, setStatus] = useState<"checking" | "up" | "down">("checking");
  const [message, setMessage] = useState<string>("");

  const check = () => {
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
  };

  useEffect(() => {
    check();
    const onUpdate = () => check();
    window.addEventListener("backendUrlUpdated", onUpdate);
    return () => window.removeEventListener("backendUrlUpdated", onUpdate);
  }, []);

  return (
    <div className="flex items-center gap-2">
      <span
        className={`inline-block h-2.5 w-2.5 rounded-full ${
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
    </div>
  );
}
