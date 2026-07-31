import { createClient } from "@/lib/supabase/server";
import AddBuyerForm from "@/components/AddBuyerForm";

function formatCents(cents: number | null): string {
  if (cents === null || cents === undefined) return "—";
  return `$${(cents / 100).toLocaleString()}`;
}

export default async function BuyersPage() {
  const supabase = createClient();

  const { data: buyers } = await supabase
    .from("buyers")
    .select("*")
    .order("deals_closed", { ascending: false })
    .limit(200);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Cash buyers</h1>
        <p className="text-white/50">
          Who a deal gets sent to once it&apos;s under contract. Buyers are matched to a property by
          price range, city, beds, and size — the ones who&apos;ve closed most are contacted first.
        </p>
      </div>

      <AddBuyerForm />

      <div className="overflow-x-auto rounded border border-white/10">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-white/10 text-white/50">
            <tr>
              <th className="p-3">Buyer</th>
              <th className="p-3">Range</th>
              <th className="p-3">Cities</th>
              <th className="p-3">Closed</th>
              <th className="p-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {(buyers ?? []).map((buyer) => (
              <tr key={buyer.id} className="hover:bg-white/5">
                <td className="p-3">
                  <div>{buyer.name}</div>
                  <div className="text-white/40">{buyer.company ?? buyer.phone ?? buyer.email}</div>
                </td>
                <td className="p-3 text-white/70">
                  {formatCents(buyer.min_price)} – {formatCents(buyer.max_price)}
                </td>
                <td className="p-3 text-white/70">
                  {(buyer.cities ?? []).length ? buyer.cities.join(", ") : "anywhere"}
                </td>
                <td className="p-3 text-white/70">{buyer.deals_closed ?? 0}</td>
                <td className="p-3 text-white/50">
                  {buyer.opted_out ? "opted out" : buyer.active ? "active" : "inactive"}
                  {buyer.proof_of_funds_on_file ? " · POF" : ""}
                </td>
              </tr>
            ))}
            {(buyers ?? []).length === 0 && (
              <tr>
                <td colSpan={5} className="p-4 text-white/40">
                  No buyers yet. This list is the thing that makes a deal sellable — add the cash
                  buyers you already know first.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
