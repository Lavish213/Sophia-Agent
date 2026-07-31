import HealthStatus from "@/components/HealthStatus";
import { createClient } from "@/lib/supabase/server";

export default async function SettingsPage() {
  const supabase = createClient();

  const { data: dnc } = await supabase
    .from("dnc_list")
    .select("phone, reason, created_at")
    .order("created_at", { ascending: false })
    .limit(200);

  const { data: optedOut } = await supabase
    .from("leads")
    .select("id, owner_phone, opted_out, email_opted_out")
    .or("opted_out.eq.true,email_opted_out.eq.true")
    .limit(200);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <section className="rounded border border-white/10 p-4">
        <h2 className="mb-3 text-lg font-medium">System health</h2>
        <HealthStatus />
      </section>

      <section>
        <h2 className="mb-1 text-lg font-medium">Do-not-call list</h2>
        <p className="mb-3 text-sm text-white/50">
          Numbers Sophia will never call or text. Added automatically when someone replies STOP,
          or when a skip-traced number fails a DNC or TCPA scrub.
        </p>
        <div className="divide-y divide-white/10 rounded border border-white/10">
          {(dnc ?? []).map((entry) => (
            <div key={entry.phone} className="flex items-center justify-between p-3 text-sm">
              <span>{entry.phone}</span>
              <span className="text-white/40">
                {entry.reason} · {new Date(entry.created_at).toLocaleDateString()}
              </span>
            </div>
          ))}
          {(dnc ?? []).length === 0 && (
            <p className="p-3 text-sm text-white/40">Nobody on the do-not-call list yet.</p>
          )}
        </div>
      </section>

      <section>
        <h2 className="mb-1 text-lg font-medium">Opted-out leads</h2>
        <p className="mb-3 text-sm text-white/50">
          Leads suppressed from outreach on one or both channels.
        </p>
        <div className="divide-y divide-white/10 rounded border border-white/10">
          {(optedOut ?? []).map((lead) => (
            <div key={lead.id} className="flex items-center justify-between p-3 text-sm">
              <span>{lead.owner_phone ?? "no phone on file"}</span>
              <span className="text-white/40">
                {[lead.opted_out ? "no texts or calls" : null, lead.email_opted_out ? "no email" : null]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </div>
          ))}
          {(optedOut ?? []).length === 0 && (
            <p className="p-3 text-sm text-white/40">No opted-out leads.</p>
          )}
        </div>
      </section>
    </div>
  );
}
