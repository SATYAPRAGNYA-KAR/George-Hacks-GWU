import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { SiteHeader } from "@/components/SiteHeader";
import { LevelBadge } from "@/components/LevelBadge";
import { api, type Alert } from "@/lib/api";
import { Loader2, RefreshCw } from "lucide-react";

export const Route = createFileRoute("/alerts")({
  component: AlertsPage,
});

function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = () =>
    api
      .alerts()
      .then((d) => setAlerts(d.alerts))
      .catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await api.refreshAlerts();
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <SiteHeader />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold text-foreground">Active alerts</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Graduated alerts triggered by composite risk scoring.
            </p>
          </div>
          <button
            onClick={refresh}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm font-medium text-card-foreground hover:bg-secondary disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            Refresh scoring
          </button>
        </div>

        {error && (
          <div className="mt-6 rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {!alerts && !error ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading…
          </div>
        ) : (
          <div className="mt-6 grid gap-4">
            {alerts?.map((a) => (
              <Link
                key={a.alert_id}
                to="/community/$communityId"
                params={{ communityId: a.community_id }}
                className="block rounded-lg border border-border bg-card p-5 transition-shadow hover:shadow-[var(--shadow-card)]"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <LevelBadge level={a.level} />
                    <h3 className="text-lg font-semibold text-card-foreground">
                      {a.community_name}
                    </h3>
                  </div>
                  <div className="text-sm tabular-nums text-muted-foreground">
                    Risk{" "}
                    <span className="font-semibold text-foreground">
                      {a.risk_score.toFixed(1)}
                    </span>
                    /100
                  </div>
                </div>
                <p className="mt-3 text-sm text-muted-foreground">{a.headline}</p>
                {a.top_factors?.length > 0 && (
                  <ul className="mt-3 space-y-1 text-sm text-foreground">
                    {a.top_factors.slice(0, 2).map((f, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="text-primary">•</span>
                        <span className="line-clamp-1">{f}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Link>
            ))}
            {alerts && alerts.length === 0 && (
              <p className="rounded-md border border-border bg-card p-6 text-center text-sm text-muted-foreground">
                No active alerts at this time.
              </p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
