import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { SiteHeader } from "@/components/SiteHeader";
import { RiskBar } from "@/components/RiskBar";
import { api, type RiskCommunity } from "@/lib/api";
import { Loader2 } from "lucide-react";

export const Route = createFileRoute("/risk")({
  head: () => ({
    meta: [
      { title: "Community Risk Scores — RootBridge" },
      {
        name: "description",
        content:
          "Composite food-supply risk scores for every monitored Louisiana community.",
      },
      { property: "og:title", content: "Community Risk Scores — RootBridge" },
      {
        property: "og:description",
        content: "Crop health, disruption, corridor and vulnerability breakdowns.",
      },
    ],
  }),
  component: RiskPage,
});

function RiskPage() {
  const [data, setData] = useState<RiskCommunity[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .risk()
      .then((d) =>
        setData(d.communities.slice().sort((a, b) => b.risk_score - a.risk_score)),
      )
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <SiteHeader />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="text-3xl font-bold text-foreground">Community risk</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Sorted by composite risk score (0–100).
        </p>

        {error && (
          <div className="mt-6 rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {!data && !error ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading…
          </div>
        ) : (
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {data?.map((c) => (
              <Link
                key={c.community_id}
                to="/community/$communityId"
                params={{ communityId: c.community_id }}
                className="block rounded-lg border border-border bg-card p-5 transition-shadow hover:shadow-[var(--shadow-card)]"
              >
                <div className="flex items-baseline justify-between">
                  <h3 className="font-semibold text-card-foreground">
                    {c.community_name}
                  </h3>
                  <span className="tabular-nums text-2xl font-bold text-foreground">
                    {c.risk_score.toFixed(1)}
                  </span>
                </div>
                <div className="mt-3">
                  <RiskBar score={c.risk_score} />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                  {Object.entries(c.components).map(([k, v]) => (
                    <div
                      key={k}
                      className="rounded-md bg-secondary px-2 py-1.5 text-secondary-foreground"
                    >
                      <div className="capitalize text-muted-foreground">
                        {k.replace(/_/g, " ")}
                      </div>
                      <div className="font-semibold tabular-nums">
                        {v.toFixed(0)}
                      </div>
                    </div>
                  ))}
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
