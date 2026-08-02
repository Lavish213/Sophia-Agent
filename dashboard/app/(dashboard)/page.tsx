import { createClient } from "@/lib/supabase/server";
import Link from "next/link";

function formatCents(cents: number | null): string {
  if (cents === null || cents === undefined) return "—";
  return `$${(cents / 100).toLocaleString()}`;
}

export default async function HomePage() {
  const supabase = createClient();

  const { data: hotLeads } = await supabase
    .from("leads")
    .select("id, stage, motivation_level, properties(address, distress_score, estimated_arv)")
    .eq("is_hot_lead", true)
    .order("updated_at", { ascending: false })
    .limit(10);

  const { data: needsYou } = await supabase
    .from("leads")
    .select("id, operator_notes, updated_at, properties(address)")
    .eq("priority_callback", true)
    .not("stage", "in", "(closed,dead)")
    .order("updated_at", { ascending: false })
    .limit(10);

  const { data: recentCalls } = await supabase
    .from("calls")
    .select("id, call_disposition, direction, created_at, leads(id, properties(address))")
    .order("created_at", { ascending: false })
    .limit(10);

  const { count: activeLeadsCount } = await supabase
    .from("leads")
    .select("id", { count: "exact", head: true })
    .not("stage", "in", "(closed,dead)");

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Overview</h1>
        <p className="text-white/50">{activeLeadsCount ?? 0} active leads in the pipeline</p>
      </div>

      {(needsYou ?? []).length > 0 && (
        <section>
          <h2 className="mb-1 text-lg font-medium text-amber-300">Waiting on you</h2>
          <p className="mb-3 text-sm text-white/50">
            Sophia handed these to you — the seller asked for a person, or it went past what she
            should answer.
          </p>
          <div className="divide-y divide-white/10 rounded border border-amber-500/30">
            {(needsYou ?? []).map((lead: any) => (
              <Link
                key={lead.id}
                href={`/leads/${lead.id}`}
                className="block p-4 hover:bg-white/5"
              >
                <div className="font-medium">{lead.properties?.address ?? "Unknown address"}</div>
                {lead.operator_notes && (
                  <div className="text-sm text-white/60">{lead.operator_notes}</div>
                )}
              </Link>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-lg font-medium">Hot leads</h2>
        <div className="divide-y divide-white/10 rounded border border-white/10">
          {(hotLeads ?? []).length === 0 && (
            <p className="p-4 text-white/40">No hot leads right now.</p>
          )}
          {(hotLeads ?? []).map((lead: any) => (
            <Link
              key={lead.id}
              href={`/leads/${lead.id}`}
              className="flex items-center justify-between p-4 hover:bg-white/5"
            >
              <span>{lead.properties?.address ?? "Unknown address"}</span>
              <span className="text-white/50">
                distress {lead.properties?.distress_score ?? "—"} · ARV{" "}
                {formatCents(lead.properties?.estimated_arv)}
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium">Recent calls</h2>
        <div className="divide-y divide-white/10 rounded border border-white/10">
          {(recentCalls ?? []).length === 0 && (
            <p className="p-4 text-white/40">No calls yet.</p>
          )}
          {(recentCalls ?? []).map((call: any) => (
            <Link
              key={call.id}
              href={`/calls/${call.id}`}
              className="flex items-center justify-between p-4 hover:bg-white/5"
            >
              <span>{call.leads?.properties?.address ?? "Unknown"}</span>
              <span className="text-white/50">
                {call.direction} · {call.call_disposition ?? "pending"}
              </span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
