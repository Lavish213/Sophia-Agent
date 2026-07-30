"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

type HealthResponse = {
  status: string;
  checks: Record<string, string>;
};

export default function HealthStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/health`)
      .then((res) => res.json())
      .then(setHealth)
      .catch(() => setError("Could not reach the backend."));
  }, []);

  if (error) {
    return <p className="text-red-400">{error}</p>;
  }

  if (!health) {
    return <p className="text-white/40">Checking...</p>;
  }

  return (
    <div className="space-y-2">
      {Object.entries(health.checks).map(([name, status]) => (
        <div key={name} className="flex items-center justify-between border-b border-white/10 py-2">
          <span className="capitalize">{name}</span>
          <span className={status === "ok" || status === "configured" ? "text-green-400" : "text-yellow-400"}>
            {status}
          </span>
        </div>
      ))}
    </div>
  );
}
