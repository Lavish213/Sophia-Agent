"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
const STAGES = ["new", "contacted", "offer_made", "walkthrough_booked", "under_contract", "closed", "dead"];

export default function LeadActions({ leadId, stage }: { leadId: string; stage: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleCallNow() {
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_URL}/api/leads/${leadId}/call`, { method: "POST" });
      const body = await res.json();
      setMessage(res.ok ? "Call placed." : `Could not place call: ${body.detail}`);
    } catch {
      setMessage("Could not reach the backend.");
    } finally {
      setBusy(false);
    }
  }

  async function handleStageChange(newStage: string) {
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_URL}/api/leads/${leadId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stage: newStage }),
      });
      if (res.ok) {
        router.refresh();
      } else {
        setMessage("Could not update stage.");
      }
    } catch {
      setMessage("Could not reach the backend.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-3">
      <select
        defaultValue={stage}
        disabled={busy}
        onChange={(e) => handleStageChange(e.target.value)}
        className="rounded border border-white/20 bg-black px-3 py-2 text-sm text-white"
      >
        {STAGES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      <button
        onClick={handleCallNow}
        disabled={busy}
        className="rounded bg-white px-4 py-2 text-sm font-medium text-black disabled:opacity-50"
      >
        {busy ? "Working..." : "Call now"}
      </button>
      {message && <span className="text-sm text-white/50">{message}</span>}
    </div>
  );
}
