import { createClient } from "@/lib/supabase/server";
import CsvUploadForm from "@/components/CsvUploadForm";

function formatCents(cents: number | null): string {
  if (cents === null || cents === undefined) return "—";
  return `$${(cents / 100).toLocaleString()}`;
}

export default async function PropertiesPage() {
  const supabase = createClient();

  const { data: properties } = await supabase
    .from("properties")
    .select("id, address, distress_score, estimated_arv, deal_viable, created_at")
    .order("created_at", { ascending: false })
    .limit(100);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Properties</h1>
      <CsvUploadForm />

      <div className="overflow-x-auto rounded border border-white/10">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-white/10 text-white/50">
            <tr>
              <th className="p-3">Address</th>
              <th className="p-3">Distress</th>
              <th className="p-3">Est. ARV</th>
              <th className="p-3">Viable</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {(properties ?? []).map((p) => (
              <tr key={p.id} className="hover:bg-white/5">
                <td className="p-3">{p.address}</td>
                <td className="p-3 text-white/70">{p.distress_score}</td>
                <td className="p-3 text-white/70">{formatCents(p.estimated_arv)}</td>
                <td className="p-3">{p.deal_viable ? "yes" : "no"}</td>
              </tr>
            ))}
            {(properties ?? []).length === 0 && (
              <tr>
                <td colSpan={4} className="p-4 text-white/40">
                  No properties yet. Upload a CSV above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
