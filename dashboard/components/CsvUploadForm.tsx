"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export default function CsvUploadForm() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const file = fileInputRef.current?.files?.[0];
    if (!file) return;

    setBusy(true);
    setResult(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_URL}/api/properties/upload`, {
        method: "POST",
        body: formData,
      });
      const body = await res.json();
      if (res.ok) {
        setResult(`Processed ${body.processed} rows, created ${body.leads_created} leads, ${body.errors} errors.`);
        router.refresh();
      } else {
        setResult(`Upload failed: ${body.detail ?? "unknown error"}`);
      }
    } catch {
      setResult("Could not reach the backend.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-3 rounded border border-white/10 p-4">
      <input ref={fileInputRef} type="file" accept=".csv" className="text-sm text-white/70" />
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-white px-4 py-2 text-sm font-medium text-black disabled:opacity-50"
      >
        {busy ? "Uploading..." : "Upload CSV"}
      </button>
      {result && <span className="text-sm text-white/50">{result}</span>}
    </form>
  );
}
