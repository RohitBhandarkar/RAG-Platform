"use client";

import { useState, useEffect } from "react";
import { getStoredApiUrl, setStoredApiUrl } from "@/lib/backend-url";
import { getApiBaseUrl } from "@/lib/api";

export default function BackendUrlSettings() {
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setValue(getStoredApiUrl() || getApiBaseUrl() || "");
  }, []);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim().replace(/\/$/, "");
    if (!trimmed) return;
    setStoredApiUrl(trimmed);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <form onSubmit={handleSave} className="flex flex-wrap items-center gap-2">
      <span className="text-xs font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap">
        Backend URL
      </span>
      <label className="min-w-0 flex-1 min-w-[200px]">
        <span className="sr-only">Backend API URL</span>
        <input
          type="url"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="https://your-vm-ip-or-domain"
          className="block w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
        />
      </label>
      <button
        type="submit"
        className="rounded-md bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700"
      >
        {saved ? "Saved" : "Save"}
      </button>
    </form>
  );
}
