"use client";

import { useState } from "react";

const FIELD_CLASS =
  "w-full rounded border border-white/20 bg-black px-3 py-2 text-white placeholder:text-white/30";

export default function SellForm() {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);

    const form = new FormData(e.currentTarget);
    const payload = Object.fromEntries(form.entries());

    try {
      const res = await fetch("/api/lead", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setDone(true);
      } else {
        const body = await res.json().catch(() => ({}));
        setError(
          body.error === "phone_or_email_required"
            ? "Please leave a phone number or an email so we can reach you."
            : "Something went wrong on our end. Please call us instead."
        );
      }
    } catch {
      setError("Something went wrong on our end. Please call us instead.");
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="rounded border border-white/20 p-6">
        <h2 className="text-xl font-medium">Got it — thank you.</h2>
        <p className="mt-2 text-white/60">
          We&apos;ll reach out shortly to talk through your property. If you&apos;d rather not wait,
          feel free to call us directly.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <input name="name" placeholder="Your name" className={FIELD_CLASS} />
      <input name="address" placeholder="Property address" className={FIELD_CLASS} />
      <div className="grid gap-3 sm:grid-cols-2">
        <input name="phone" type="tel" placeholder="Phone number" className={FIELD_CLASS} />
        <input name="email" type="email" placeholder="Email" className={FIELD_CLASS} />
      </div>
      <select name="timeline" defaultValue="" className={FIELD_CLASS}>
        <option value="">How soon are you looking to sell?</option>
        <option value="ASAP">As soon as possible</option>
        <option value="1-3 months">In the next few months</option>
        <option value="6+ months">Sometime this year</option>
        <option value="just curious">Just curious what it&apos;s worth</option>
      </select>
      <select name="condition" defaultValue="" className={FIELD_CLASS}>
        <option value="">What kind of shape is it in?</option>
        <option value="move-in ready">Move-in ready</option>
        <option value="needs minor work">Needs some work</option>
        <option value="needs major work">Needs major work</option>
      </select>
      <textarea
        name="message"
        rows={3}
        placeholder="Anything else we should know? (optional)"
        className={FIELD_CLASS}
      />

      <input
        name="company"
        tabIndex={-1}
        autoComplete="off"
        aria-hidden="true"
        className="hidden"
      />

      {error && <p className="text-sm text-red-400">{error}</p>}

      <button
        type="submit"
        disabled={busy}
        className="w-full rounded bg-white px-4 py-3 font-medium text-black disabled:opacity-50"
      >
        {busy ? "Sending..." : "Get my cash offer"}
      </button>
    </form>
  );
}
