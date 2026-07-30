import { createClient } from "@/lib/supabase/server";
import { notFound } from "next/navigation";
import Link from "next/link";
import LeadActions from "@/components/LeadActions";

function formatCents(cents: number | null): string {
  if (cents === null || cents === undefined) return "—";
  return `$${(cents / 100).toLocaleString()}`;
}

export default async function LeadDetailPage({ params }: { params: { id: string } }) {
  const supabase = createClient();
  const { id } = params;

  const { data: lead } = await supabase
    .from("leads")
    .select("*, properties(*)")
    .eq("id", id)
    .single();

  if (!lead) notFound();

  const { data: calls } = await supabase
    .from("calls")
    .select("id, direction, call_disposition, call_summary, created_at")
    .eq("lead_id", id)
    .order("created_at", { ascending: false });

  const { data: offers } = await supabase
    .from("offers")
    .select("id, amount, status, created_at")
    .eq("lead_id", id)
    .order("created_at", { ascending: false });

  const prop = lead.properties ?? {};
  const callBrief = lead.call_brief as Record<string, any> | null;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{prop.address ?? "Unknown address"}</h1>
          <p className="text-white/50">
            {prop.city}, {prop.state} {prop.zip} · distress {prop.distress_score ?? "—"}
          </p>
        </div>
        <LeadActions leadId={id} stage={lead.stage} />
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="rounded border border-white/10 p-4">
          <p className="text-white/50">Estimated ARV</p>
          <p className="text-xl">{formatCents(prop.estimated_arv)}</p>
        </div>
        <div className="rounded border border-white/10 p-4">
          <p className="text-white/50">Offer range (MAO)</p>
          <p className="text-xl">{formatCents(prop.mao)}</p>
        </div>
        <div className="rounded border border-white/10 p-4">
          <p className="text-white/50">Motivation</p>
          <p className="text-xl">{lead.motivation_level ?? "—"}/10</p>
        </div>
      </div>

      {callBrief && (
        <section className="rounded border border-white/10 p-4">
          <h2 className="mb-2 text-lg font-medium">Bob&apos;s call brief</h2>
          <p className="text-white/70">
            Phase {callBrief.phase} · Objective: {callBrief.objective}
          </p>
          <p className="text-white/50">Mood: {callBrief.mood}</p>
          {callBrief.avoid?.length > 0 && (
            <p className="text-white/50">Avoid: {callBrief.avoid.join(", ")}</p>
          )}
        </section>
      )}

      {lead.call_summary && (
        <section className="rounded border border-white/10 p-4">
          <h2 className="mb-2 text-lg font-medium">Latest call summary</h2>
          <p className="text-white/70">{lead.call_summary}</p>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-lg font-medium">Calls</h2>
        <div className="divide-y divide-white/10 rounded border border-white/10">
          {(calls ?? []).map((call) => (
            <Link
              key={call.id}
              href={`/calls/${call.id}`}
              className="flex items-center justify-between p-4 hover:bg-white/5"
            >
              <span>{call.direction} call</span>
              <span className="text-white/50">{call.call_disposition ?? "pending"}</span>
            </Link>
          ))}
          {(calls ?? []).length === 0 && <p className="p-4 text-white/40">No calls yet.</p>}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium">Offers</h2>
        <div className="divide-y divide-white/10 rounded border border-white/10">
          {(offers ?? []).map((offer) => (
            <div key={offer.id} className="flex items-center justify-between p-4">
              <span>{formatCents(offer.amount)}</span>
              <span className="text-white/50">{offer.status}</span>
            </div>
          ))}
          {(offers ?? []).length === 0 && <p className="p-4 text-white/40">No offers yet.</p>}
        </div>
      </section>
    </div>
  );
}
