import { createClient } from "@/lib/supabase/server";
import { notFound } from "next/navigation";

export default async function CallDetailPage({ params }: { params: { id: string } }) {
  const supabase = createClient();
  const { id } = params;

  const { data: call } = await supabase
    .from("calls")
    .select("*, leads(id, properties(address))")
    .eq("id", id)
    .single();

  if (!call) notFound();

  const { data: chunks } = await supabase
    .from("transcript_chunks")
    .select("speaker, text, sequence_order")
    .eq("call_id", id)
    .order("sequence_order", { ascending: true });

  const { data: events } = await supabase
    .from("call_events")
    .select("event_type, payload, created_at")
    .eq("call_id", id)
    .order("created_at", { ascending: true });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{call.leads?.properties?.address ?? "Unknown"}</h1>
        <p className="text-white/50">
          {call.direction} · {call.call_disposition ?? "pending"} ·{" "}
          {new Date(call.created_at).toLocaleString()}
          {call.answered_by ? ` · answered by ${call.answered_by}` : ""}
          {call.voicemail_left ? " · voicemail left" : ""}
        </p>
      </div>

      <section>
        <h2 className="mb-3 text-lg font-medium">What happened</h2>
        <div className="divide-y divide-white/10 rounded border border-white/10">
          {(events ?? []).map((event, i) => (
            <div key={i} className="flex items-baseline justify-between p-3 text-sm">
              <span className="text-white/80">{event.event_type.replace(/_/g, " ")}</span>
              <span className="text-white/40">
                {new Date(event.created_at).toLocaleTimeString()}
              </span>
            </div>
          ))}
          {(events ?? []).length === 0 && (
            <p className="p-3 text-sm text-white/40">No events recorded for this call.</p>
          )}
        </div>
      </section>

      {call.call_summary && (
        <section className="rounded border border-white/10 p-4">
          <h2 className="mb-2 text-lg font-medium">Summary</h2>
          <p className="text-white/70">{call.call_summary}</p>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-lg font-medium">Transcript</h2>
        <div className="space-y-3 rounded border border-white/10 p-4">
          {(chunks ?? []).map((chunk, i) => (
            <div key={i}>
              <span className="font-medium text-white/70">
                {chunk.speaker === "sophia" ? "Sophia" : "Seller"}:
              </span>{" "}
              <span className="text-white/60">{chunk.text}</span>
            </div>
          ))}
          {(chunks ?? []).length === 0 && (
            <p className="text-white/40">No transcript recorded for this call.</p>
          )}
        </div>
      </section>
    </div>
  );
}
