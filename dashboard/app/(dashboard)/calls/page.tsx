import { createClient } from "@/lib/supabase/server";
import Link from "next/link";

export default async function CallsPage() {
  const supabase = createClient();

  const { data: calls } = await supabase
    .from("calls")
    .select("id, direction, call_disposition, duration_seconds, created_at, leads(properties(address))")
    .order("created_at", { ascending: false })
    .limit(100);

  return (
    <div>
      <h1 className="mb-4 text-2xl font-semibold">Calls</h1>
      <div className="overflow-x-auto rounded border border-white/10">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-white/10 text-white/50">
            <tr>
              <th className="p-3">Address</th>
              <th className="p-3">Direction</th>
              <th className="p-3">Disposition</th>
              <th className="p-3">Duration</th>
              <th className="p-3">When</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {(calls ?? []).map((call: any) => (
              <tr key={call.id} className="hover:bg-white/5">
                <td className="p-3">
                  <Link href={`/calls/${call.id}`} className="hover:underline">
                    {call.leads?.properties?.address ?? "Unknown"}
                  </Link>
                </td>
                <td className="p-3 text-white/70">{call.direction}</td>
                <td className="p-3 text-white/70">{call.call_disposition ?? "pending"}</td>
                <td className="p-3 text-white/70">{call.duration_seconds ? `${call.duration_seconds}s` : "—"}</td>
                <td className="p-3 text-white/50">{new Date(call.created_at).toLocaleString()}</td>
              </tr>
            ))}
            {(calls ?? []).length === 0 && (
              <tr>
                <td colSpan={5} className="p-4 text-white/40">
                  No calls yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
