"use client";

import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
const REFRESH_MS = 30000;

type WorkerStatus = {
  worker: string;
  state: "ok" | "late" | "stale" | "error" | "never_run";
  interval_minutes: number;
  last_run: string | null;
  minutes_since: number | null;
  results: Record<string, unknown>;
  error: string | null;
  duration_ms?: number;
};

const STATE_STYLE: Record<string, string> = {
  ok: "bg-emerald-500/15 text-emerald-300",
  late: "bg-amber-500/15 text-amber-300",
  stale: "bg-red-500/15 text-red-300",
  error: "bg-red-500/15 text-red-300",
  never_run: "bg-white/10 text-white/50",
};

const STATE_LABEL: Record<string, string> = {
  ok: "running",
  late: "late",
  stale: "not running",
  error: "erroring",
  never_run: "never run",
};

const WORKER_JOB: Record<string, string> = {
  bob: "writes each lead's call plan",
  dialer: "places the outbound calls",
  discovery: "finds leads and skip traces",
};

function describe(status: WorkerStatus): string {
  if (status.state === "never_run") return "No run recorded yet.";
  if (status.minutes_since === null) return "Last run time unknown.";
  if (status.minutes_since < 1) return "Ran just now.";
  if (status.minutes_since < 60) return `Ran ${status.minutes_since} min ago.`;
  const hours = Math.floor(status.minutes_since / 60);
  return `Ran ${hours}h ago.`;
}

function summarize(results: Record<string, unknown>): string {
  const parts = Object.entries(results)
    .filter(([, v]) => typeof v === "number" && v > 0)
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`);
  return parts.length ? parts.join(" · ") : "nothing to do last cycle";
}

export default function WorkerHealth() {
  const [data, setData] = useState<{ overall: string; workers: WorkerStatus[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/workers/health`, { cache: "no-store" });
      if (!res.ok) throw new Error("bad response");
      setData(await res.json());
      setError(null);
    } catch {
      setError("Can't reach the backend — the web service itself may be down.");
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  if (error) {
    return <p className="rounded border border-red-500/30 bg-red-500/10 p-4 text-red-300">{error}</p>;
  }

  if (!data) {
    return <p className="rounded border border-white/10 p-4 text-white/40">Checking workers...</p>;
  }

  return (
    <div className="space-y-3">
      {data.workers.map((w) => (
        <div key={w.worker} className="rounded border border-white/10 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="font-medium">{w.worker}</span>
              <span className="ml-2 text-sm text-white/40">{WORKER_JOB[w.worker]}</span>
            </div>
            <span className={`rounded px-2 py-0.5 text-xs ${STATE_STYLE[w.state]}`}>
              {STATE_LABEL[w.state]}
            </span>
          </div>

          <p className="mt-2 text-sm text-white/60">
            {describe(w)} Expected every {w.interval_minutes} min.
          </p>

          {w.state !== "never_run" && (
            <p className="mt-1 text-sm text-white/40">Last cycle — {summarize(w.results)}</p>
          )}

          {w.error && (
            <p className="mt-2 rounded bg-red-500/10 p-2 text-sm text-red-300">{w.error}</p>
          )}
        </div>
      ))}
    </div>
  );
}
