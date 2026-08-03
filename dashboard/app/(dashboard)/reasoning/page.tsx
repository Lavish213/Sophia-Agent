import Link from "next/link";
import { createClient } from "@/lib/supabase/server";

const BOX_MEANING: Record<string, string> = {
  right_person: "confirm they actually own it",
  property_confirmed: "confirm which property",
  occupancy: "find out who lives there",
  condition: "find out what needs work",
  timeline: "find out how soon",
  motivation: "find out why they'd sell",
  next_step: "book the walkthrough",
};

const MOOD_STYLE: Record<string, string> = {
  distressed: "bg-red-500/15 text-red-300",
  guarded: "bg-amber-500/15 text-amber-300",
  motivated: "bg-emerald-500/15 text-emerald-300",
};

function confidenceLabel(value: number | null): string {
  if (value === null || value === undefined) return "unknown";
  if (value >= 0.8) return "high";
  if (value >= 0.6) return "medium";
  return "low";
}

export default async function ReasoningPage() {
  const supabase = createClient();

  const { data: queue } = await supabase
    .from("leads")
    .select("id, call_priority, priority_reasons, waiting_on_human, properties(address)")
    .eq("callable", true)
    .eq("opted_out", false)
    .not("stage", "in", "(closed,dead)")
    .order("waiting_on_human", { ascending: false })
    .order("call_priority", { ascending: false })
    .limit(15);

  const { data: records } = await supabase
    .from("decision_records")
    .select("*, leads(id, properties(address))")
    .eq("decision_type", "call_brief")
    .order("created_at", { ascending: false })
    .limit(100);

  const rows = records ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Bob&apos;s reasoning</h1>
        <p className="text-white/50">
          The plan Bob wrote for each lead before Sophia called, and what he based it on. If the
          plans look wrong here, the calls will go wrong too.
        </p>
      </div>

      <section>
        <h2 className="mb-1 text-lg font-medium">Who Bob would call next</h2>
        <p className="mb-3 text-sm text-white/50">
          Ranked by what he knows, not just the distress score. Anyone who asked for a callback
          goes first regardless of how the property scores.
        </p>
        <div className="divide-y divide-white/10 rounded border border-white/10">
          {(queue ?? []).map((lead: any, i: number) => (
            <Link key={lead.id} href={`/leads/${lead.id}`} className="block p-3 hover:bg-white/5">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm">
                  <span className="mr-2 text-white/30">{i + 1}</span>
                  {lead.properties?.address ?? "Unknown address"}
                </span>
                <span className="shrink-0 text-sm text-white/40">
                  {lead.waiting_on_human ? "waiting on you · " : ""}
                  {lead.call_priority ?? 0}
                </span>
              </div>
              {(lead.priority_reasons ?? []).length > 0 && (
                <div className="mt-1 text-xs text-white/35">
                  {(lead.priority_reasons as string[]).join(" · ")}
                </div>
              )}
            </Link>
          ))}
          {(queue ?? []).length === 0 && (
            <p className="p-3 text-sm text-white/40">
              No callable leads ranked yet. Bob scores each lead when he writes its brief.
            </p>
          )}
        </div>
      </section>

      <div className="space-y-3">
        {rows.map((record) => {
          const output = (record.output ?? {}) as Record<string, unknown>;
          const inputs = (record.inputs_used ?? {}) as Record<string, unknown>;
          const address = record.leads?.properties?.address ?? "Unknown address";
          const missingBox = String(output.missing_box ?? "");
          const mood = String(output.mood ?? "");

          return (
            <div key={record.id} className="rounded border border-white/10 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                {record.leads?.id ? (
                  <Link href={`/leads/${record.leads.id}`} className="font-medium hover:underline">
                    {address}
                  </Link>
                ) : (
                  <span className="font-medium">{address}</span>
                )}
                <div className="flex items-center gap-2 text-xs">
                  {mood && (
                    <span className={`rounded px-2 py-0.5 ${MOOD_STYLE[mood] ?? "bg-white/10 text-white/50"}`}>
                      {mood}
                    </span>
                  )}
                  <span className="text-white/40">
                    {confidenceLabel(record.confidence)} confidence
                  </span>
                </div>
              </div>

              <p className="mt-2 text-sm text-white/80">{String(output.objective ?? "")}</p>

              {missingBox && (
                <p className="mt-1 text-sm text-white/50">
                  Going after: {BOX_MEANING[missingBox] ?? missingBox.replace(/_/g, " ")}
                  {output.phase ? ` · phase ${output.phase}` : ""}
                </p>
              )}

              {Boolean(output.opener_hint) && (
                <p className="mt-1 text-sm text-white/50">Opener: {String(output.opener_hint)}</p>
              )}

              {Array.isArray(output.avoid) && output.avoid.length > 0 && (
                <p className="mt-1 text-sm text-amber-300/70">
                  Avoid: {(output.avoid as string[]).join("; ")}
                </p>
              )}

              <p className="mt-3 text-xs text-white/30">
                Decided from — situation: {String(inputs.situation_label ?? "unknown")} · prior calls:{" "}
                {String(inputs.call_count ?? 0)} · intel: {String(inputs.packet_state ?? "missing")}
                {" · "}
                {new Date(record.created_at).toLocaleString()}
              </p>

              {Array.isArray(record.reason_codes) && record.reason_codes.length > 0 && (
                <p className="mt-1 font-mono text-xs text-white/25">
                  {record.reason_codes.join("  ")}
                </p>
              )}
            </div>
          );
        })}

        {rows.length === 0 && (
          <p className="rounded border border-white/10 p-4 text-white/40">
            No call plans yet. Bob writes one per lead each cycle — this fills in once the worker
            has run against real leads.
          </p>
        )}
      </div>
    </div>
  );
}
