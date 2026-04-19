import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { SiteHeader } from "@/components/SiteHeader";
import { LevelBadge } from "@/components/LevelBadge";
import { RiskBar } from "@/components/RiskBar";
import { api, type Alert, type RiskCommunity } from "@/lib/api";
import { AlertTriangle, Activity, MapPin, ArrowRight, Loader2 } from "lucide-react";

export const Route = createFileRoute("/")({
  component: HomePage,
});

function HomePage() {
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [risk, setRisk] = useState<RiskCommunity[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.alerts(), api.risk()])
      .then(([a, r]) => {
        setAlerts(a.alerts);
        setRisk(r.communities);
      })
      .catch((e) => setError(e.message));
  }, []);

  const loading = !alerts || !risk;
  const topAlerts = (alerts ?? []).slice(0, 4);
  const avgRisk =
    risk && risk.length
      ? risk.reduce((s, c) => s + c.risk_score, 0) / risk.length
      : 0;

  return (
    <div className="min-h-screen bg-background">
      <SiteHeader />

      <section
        className="border-b border-border"
        style={{ background: "var(--gradient-hero)" }}
      >
        <div className="mx-auto max-w-6xl px-4 py-12 text-primary-foreground sm:py-16">
          <p className="text-sm font-medium uppercase tracking-wider opacity-80">
            Louisiana · Food Supply Intelligence
          </p>
          <h1 className="mt-2 text-3xl font-bold leading-tight sm:text-5xl">
            Catch food crises before they reach the table.
          </h1>
          <p className="mt-4 max-w-2xl text-base opacity-90 sm:text-lg">
            RootBridge fuses NASA crop health, supply corridors, and community
            vulnerability into one risk score — so coordinators can act early.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to="/alerts"
              className="inline-flex items-center gap-2 rounded-md bg-background px-4 py-2 text-sm font-medium text-foreground shadow-sm hover:opacity-90"
            >
              View active alerts <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              to="/risk"
              className="inline-flex items-center gap-2 rounded-md border border-primary-foreground/30 px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary-foreground/10"
            >
              Risk by community
            </Link>
          </div>
        </div>
      </section>

      <main className="mx-auto max-w-6xl px-4 py-10">
        {error && (
          <div className="mb-6 rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            Couldn't reach the API: {error}
          </div>
        )}

        {loading && !error ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading live data…
          </div>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <Stat
                icon={<AlertTriangle className="h-5 w-5" />}
                label="Active alerts"
                value={alerts?.length ?? 0}
              />
              <Stat
                icon={<MapPin className="h-5 w-5" />}
                label="Communities monitored"
                value={risk?.length ?? 0}
              />
              <Stat
                icon={<Activity className="h-5 w-5" />}
                label="Avg risk score"
                value={avgRisk.toFixed(1)}
              />
            </div>

            <div className="mt-10 grid gap-6 lg:grid-cols-2">
              <section>
                <div className="mb-3 flex items-end justify-between">
                  <h2 className="text-xl font-semibold text-foreground">
                    Latest alerts
                  </h2>
                  <Link
                    to="/alerts"
                    className="text-sm text-primary hover:underline"
                  >
                    See all
                  </Link>
                </div>
                <div className="space-y-3">
                  {topAlerts.map((a) => (
                    <Link
                      key={a.alert_id}
                      to="/community/$communityId"
                      params={{ communityId: a.community_id }}
                      className="block rounded-lg border border-border bg-card p-4 transition-shadow hover:shadow-[var(--shadow-card)]"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="font-medium text-card-foreground">
                          {a.community_name}
                        </div>
                        <LevelBadge level={a.level} />
                      </div>
                      <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
                        {a.headline}
                      </p>
                    </Link>
                  ))}
                  {topAlerts.length === 0 && (
                    <p className="text-sm text-muted-foreground">
                      No active alerts.
                    </p>
                  )}
                </div>
              </section>

              <section>
                <div className="mb-3 flex items-end justify-between">
                  <h2 className="text-xl font-semibold text-foreground">
                    Highest-risk communities
                  </h2>
                  <Link to="/risk" className="text-sm text-primary hover:underline">
                    Full breakdown
                  </Link>
                </div>
                <div className="space-y-3">
                  {(risk ?? [])
                    .slice()
                    .sort((a, b) => b.risk_score - a.risk_score)
                    .slice(0, 5)
                    .map((c) => (
                      <Link
                        key={c.community_id}
                        to="/community/$communityId"
                        params={{ communityId: c.community_id }}
                        className="block rounded-lg border border-border bg-card p-4 transition-shadow hover:shadow-[var(--shadow-card)]"
                      >
                        <div className="mb-2 flex items-center justify-between">
                          <span className="font-medium text-card-foreground">
                            {c.community_name}
                          </span>
                          <span className="tabular-nums text-sm font-semibold text-foreground">
                            {c.risk_score.toFixed(1)}
                          </span>
                        </div>
                        <RiskBar score={c.risk_score} />
                      </Link>
                    ))}
                </div>
              </section>
            </div>
          </>
        )}
      </main>

      <footer className="border-t border-border py-6 text-center text-xs text-muted-foreground">
        Powered by RootBridge API · NASA LANCE & SMAP
      </footer>
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-5 shadow-[var(--shadow-card)]">
      <div className="flex items-center gap-2 text-muted-foreground">
        {icon}
        <span className="text-sm">{label}</span>
      </div>
      <div className="mt-2 text-3xl font-bold tabular-nums text-card-foreground">
        {value}
      </div>
    </div>
  );
}
