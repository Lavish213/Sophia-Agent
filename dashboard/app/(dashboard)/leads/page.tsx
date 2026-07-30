import { createClient } from "@/lib/supabase/server";
import Link from "next/link";

function formatCents(cents: number | null): string {
  if (cents === null || cents === undefined) return "—";
  return `$${(cents / 100).toLocaleString()}`;
}

const SOURCE_LABELS: Record<string, string> = {
  web_form: "Website form",
  inbound_call: "Called in",
  inbound_sms: "Texted in",
  reddit: "Reddit",
  skiptrace: "Skip traced",
  csv_import: "CSV",
};

export default async function LeadsPage() {
  const supabase = createClient();

  const { data: leads } = await supabase
    .from("leads")
    .select(
      "id, stage, is_hot_lead, motivation_level, owner_phone, updated_at, properties(address, distress_score, estimated_arv, source)"
    )
    .order("updated_at", { ascending: false })
    .limit(100);

  return (
    <div>
      <h1 className="mb-4 text-2xl font-semibold">Leads</h1>
      <div className="overflow-x-auto rounded border border-white/10">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-white/10 text-white/50">
            <tr>
              <th className="p-3">Address</th>
              <th className="p-3">Source</th>
              <th className="p-3">Stage</th>
              <th className="p-3">Distress</th>
              <th className="p-3">Est. ARV</th>
              <th className="p-3">Hot</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {(leads ?? []).map((lead: any) => (
              <tr key={lead.id} className="hover:bg-white/5">
                <td className="p-3">
                  <Link href={`/leads/${lead.id}`} className="hover:underline">
                    {lead.properties?.address ?? "Unknown address"}
                  </Link>
                </td>
                <td className="p-3 text-white/50">
                  {SOURCE_LABELS[lead.properties?.source] ?? lead.properties?.source ?? "—"}
                  {!lead.owner_phone && (
                    <span className="ml-2 rounded bg-amber-500/20 px-1.5 py-0.5 text-xs text-amber-300">
                      no phone
                    </span>
                  )}
                </td>
                <td className="p-3 text-white/70">{lead.stage}</td>
                <td className="p-3 text-white/70">{lead.properties?.distress_score ?? "—"}</td>
                <td className="p-3 text-white/70">{formatCents(lead.properties?.estimated_arv)}</td>
                <td className="p-3">{lead.is_hot_lead ? "🔥" : ""}</td>
              </tr>
            ))}
            {(leads ?? []).length === 0 && (
              <tr>
                <td colSpan={6} className="p-4 text-white/40">
                  No leads yet. Upload a properties CSV to get started.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
