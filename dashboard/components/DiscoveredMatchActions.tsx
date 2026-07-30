"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export default function DiscoveredMatchActions({ matchId }: { matchId: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [address, setAddress] = useState("");
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");

  async function handleConvert(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_URL}/api/discovery/reddit-matches/${matchId}/convert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address, owner_phone: phone, owner_name: name || undefined, owner_email: email || undefined }),
      });
      const body = await res.json();
      if (res.ok) {
        setMessage("Converted to lead.");
        router.refresh();
      } else {
        setMessage(`Could not convert: ${body.detail}`);
      }
    } catch {
      setMessage("Could not reach the backend.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDismiss() {
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_URL}/api/discovery/reddit-matches/${matchId}/dismiss`, { method: "POST" });
      if (res.ok) {
        router.refresh();
      } else {
        setMessage("Could not dismiss.");
      }
    } catch {
      setMessage("Could not reach the backend.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div className="flex gap-2">
        <button
          onClick={() => setOpen(true)}
          className="rounded bg-white px-3 py-1.5 text-sm font-medium text-black"
        >
          Convert to lead
        </button>
        <button
          onClick={handleDismiss}
          disabled={busy}
          className="rounded border border-white/20 px-3 py-1.5 text-sm text-white/70 disabled:opacity-50"
        >
          Dismiss
        </button>
        {message && <span className="text-sm text-white/50">{message}</span>}
      </div>
    );
  }

  return (
    <form onSubmit={handleConvert} className="space-y-2 rounded border border-white/10 p-3">
      <p className="text-sm text-white/50">
        Reddit doesn&apos;t give a phone number — add what you found (e.g. by replying to the post) to turn this into a real lead.
      </p>
      <input
        required
        placeholder="Property address"
        value={address}
        onChange={(e) => setAddress(e.target.value)}
        className="w-full rounded border border-white/20 bg-black px-2 py-1 text-sm text-white"
      />
      <input
        required
        placeholder="Owner phone"
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
        className="w-full rounded border border-white/20 bg-black px-2 py-1 text-sm text-white"
      />
      <input
        placeholder="Owner name (optional)"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="w-full rounded border border-white/20 bg-black px-2 py-1 text-sm text-white"
      />
      <input
        placeholder="Owner email (optional)"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="w-full rounded border border-white/20 bg-black px-2 py-1 text-sm text-white"
      />
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-white px-3 py-1.5 text-sm font-medium text-black disabled:opacity-50"
        >
          {busy ? "Saving..." : "Create lead"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded border border-white/20 px-3 py-1.5 text-sm text-white/70"
        >
          Cancel
        </button>
      </div>
      {message && <p className="text-sm text-white/50">{message}</p>}
    </form>
  );
}
