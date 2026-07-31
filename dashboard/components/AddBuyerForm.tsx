"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
const FIELD =
  "rounded border border-white/20 bg-black px-2 py-1 text-sm text-white placeholder:text-white/30";

function toCents(dollars: string): number | null {
  const parsed = parseFloat(dollars);
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : null;
}

export default function AddBuyerForm() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);

    const form = new FormData(e.currentTarget);
    const cities = String(form.get("cities") ?? "")
      .split(",")
      .map((c) => c.trim())
      .filter(Boolean);

    try {
      const res = await fetch(`${API_URL}/api/buyers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.get("name"),
          company: form.get("company") || null,
          phone: form.get("phone") || null,
          email: form.get("email") || null,
          min_price: toCents(String(form.get("min_price") ?? "")),
          max_price: toCents(String(form.get("max_price") ?? "")),
          cities,
          proof_of_funds_on_file: form.get("pof") === "on",
        }),
      });
      if (res.ok) {
        setOpen(false);
        router.refresh();
      } else {
        const body = await res.json().catch(() => ({}));
        setMessage(
          body.detail === "phone_or_email_required"
            ? "Add a phone or an email so deals can reach them."
            : "Could not save that buyer."
        );
      }
    } catch {
      setMessage("Could not reach the backend.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div className="flex items-center gap-3">
        <button
          onClick={() => setOpen(true)}
          className="rounded bg-white px-3 py-1.5 text-sm font-medium text-black"
        >
          Add buyer
        </button>
        {message && <span className="text-sm text-white/50">{message}</span>}
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 rounded border border-white/10 p-4">
      <div className="grid gap-2 sm:grid-cols-2">
        <input required name="name" placeholder="Buyer name" className={FIELD} />
        <input name="company" placeholder="Company (optional)" className={FIELD} />
        <input name="phone" placeholder="Phone" className={FIELD} />
        <input name="email" placeholder="Email" className={FIELD} />
        <input name="min_price" type="number" step="any" placeholder="Min price (dollars)" className={FIELD} />
        <input name="max_price" type="number" step="any" placeholder="Max price (dollars)" className={FIELD} />
      </div>
      <input name="cities" placeholder="Cities they buy in, comma separated (blank = anywhere)" className={`${FIELD} w-full`} />
      <label className="flex items-center gap-2 text-sm text-white/60">
        <input type="checkbox" name="pof" />
        Proof of funds on file
      </label>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-white px-3 py-1.5 text-sm font-medium text-black disabled:opacity-50"
        >
          {busy ? "Saving..." : "Save buyer"}
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
