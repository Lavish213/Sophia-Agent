import { createClient } from "@/lib/supabase/server";
import DiscoveredMatchActions from "@/components/DiscoveredMatchActions";

const INTENT_COLOR: Record<string, string> = {
  hot: "text-red-400",
  warm: "text-yellow-400",
  cold: "text-blue-400",
};

export default async function DiscoveredPage() {
  const supabase = createClient();

  const { data: matches } = await supabase
    .from("reddit_matches")
    .select("*")
    .eq("status", "new")
    .order("intent_score", { ascending: false })
    .limit(100);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Discovered leads</h1>
        <p className="text-white/50">
          Found automatically by monitoring San Joaquin-area subreddits for seller intent. These are not
          contactable leads yet — convert one once you have a phone number for the poster.
        </p>
      </div>

      <div className="space-y-3">
        {(matches ?? []).map((match) => (
          <div key={match.id} className="rounded border border-white/10 p-4">
            <div className="flex items-start justify-between">
              <div>
                <a href={match.url} target="_blank" rel="noreferrer" className="font-medium hover:underline">
                  {match.title}
                </a>
                <p className="text-sm text-white/50">
                  r/{match.subreddit} · u/{match.author} ·{" "}
                  <span className={INTENT_COLOR[match.intent_label] ?? "text-white/50"}>
                    {match.intent_label} ({match.intent_score})
                  </span>
                </p>
                {match.body && <p className="mt-2 text-sm text-white/70">{match.body.slice(0, 300)}</p>}
              </div>
            </div>
            <div className="mt-3">
              <DiscoveredMatchActions matchId={match.id} />
            </div>
          </div>
        ))}
        {(matches ?? []).length === 0 && (
          <p className="rounded border border-white/10 p-4 text-white/40">
            No new matches. The discovery worker checks every REDDIT_POLL_INTERVAL_MINUTES.
          </p>
        )}
      </div>
    </div>
  );
}
