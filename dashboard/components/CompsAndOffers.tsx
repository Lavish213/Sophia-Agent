"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

type Comp = {
  id: string;
  address: string | null;
  sold_price: number | null;
  sqft: number | null;
  sold_date: string | null;
};

function formatCents(cents: number | null): string {
  if (cents === null || cents === undefined) return "—";
  return `$${(cents / 100).toLocaleString()}`;
}

export default function CompsAndOffers({
  propertyId,
  leadId,
  comps,
}: {
  propertyId: string | null;
  leadId: string;
  comps: Comp[];
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [address, setAddress] = useState("");
  const [price, setPrice] = useState("");
  const [sqft, setSqft] = useState("");
  const [soldDate, setSoldDate] = useState("");

  async function handleAddComp(e: React.FormEvent) {
    e.preventDefault();
    if (!propertyId) return;
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_URL}/api/properties/${propertyId}/comps`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address: address || null,
          sold_price: Math.round(parseFloat(price) * 100),
          sqft: parseInt(sqft, 10),
          sold_date: soldDate || null,
        }),
      });
      if (res.ok) {
        const result = await res.json();
        setMessage(`Saved. ARV now ${formatCents(result.estimated_arv)}.`);
        setAddress("");
        setPrice("");
        setSqft("");
        setSoldDate("");
        setOpen(false);
        router.refresh();
      } else {
        setMessage("Could not save that comp.");
      }
    } catch {
      setMessage("Could not reach the backend.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRecalculate() {
    if (!propertyId) return;
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_URL}/api/properties/${propertyId}/comps/recalculate`, {
        method: "POST",
      });
      if (res.ok) {
        const result = await res.json();
        setMessage(`ARV ${formatCents(result.estimated_arv)}, offer ${formatCents(result.mao)}.`);
        router.refresh();
      } else {
        setMessage("Could not recalculate.");
      }
    } catch {
      setMessage("Could not reach the backend.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateOffer() {
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_URL}/api/leads/${leadId}/offers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (res.ok) {
        setMessage("Offer drafted from the current ARV.");
        router.refresh();
      } else {
        setMessage("Could not create an offer.");
      }
    } catch {
      setMessage("Could not reach the backend.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setOpen(!open)}
          disabled={!propertyId}
          className="rounded bg-white px-3 py-1.5 text-sm font-medium text-black disabled:opacity-40"
        >
          Add comp
        </button>
        <button
          onClick={handleRecalculate}
          disabled={busy || !propertyId}
          className="rounded border border-white/20 px-3 py-1.5 text-sm text-white/70 disabled:opacity-40"
        >
          Recalculate ARV
        </button>
        <button
          onClick={handleCreateOffer}
          disabled={busy}
          className="rounded border border-white/20 px-3 py-1.5 text-sm text-white/70 disabled:opacity-40"
        >
          Draft offer
        </button>
        {message && <span className="text-sm text-white/50">{message}</span>}
      </div>

      {open && (
        <form onSubmit={handleAddComp} className="space-y-2 rounded border border-white/10 p-3">
          <input
            placeholder="Comp address (optional)"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            className="w-full rounded border border-white/20 bg-black px-2 py-1 text-sm text-white"
          />
          <div className="flex gap-2">
            <input
              required
              type="number"
              step="any"
              placeholder="Sold price (dollars)"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              className="w-full rounded border border-white/20 bg-black px-2 py-1 text-sm text-white"
            />
            <input
              required
              type="number"
              placeholder="Sqft"
              value={sqft}
              onChange={(e) => setSqft(e.target.value)}
              className="w-full rounded border border-white/20 bg-black px-2 py-1 text-sm text-white"
            />
            <input
              type="date"
              value={soldDate}
              onChange={(e) => setSoldDate(e.target.value)}
              className="w-full rounded border border-white/20 bg-black px-2 py-1 text-sm text-white"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-white px-3 py-1.5 text-sm font-medium text-black disabled:opacity-50"
          >
            {busy ? "Saving..." : "Save comp"}
          </button>
        </form>
      )}

      <div className="divide-y divide-white/10 rounded border border-white/10">
        {comps.map((comp) => (
          <div key={comp.id} className="flex items-center justify-between p-3 text-sm">
            <span>{comp.address ?? "Comp"}</span>
            <span className="text-white/50">
              {formatCents(comp.sold_price)} · {comp.sqft ?? "—"} sqft
              {comp.sold_date ? ` · ${comp.sold_date}` : ""}
            </span>
          </div>
        ))}
        {comps.length === 0 && (
          <p className="p-3 text-sm text-white/40">
            No comps yet. ARV and the offer range stay empty until you add a few.
          </p>
        )}
      </div>
    </div>
  );
}
