import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { SiteHeader } from "@/components/SiteHeader";
import { LevelBadge } from "@/components/LevelBadge";
import { RiskBar } from "@/components/RiskBar";
import { api, type Alert, type RiskCommunity } from "@/lib/api";
import { ArrowLeft, Loader2, MessageSquare, Phone, CheckSquare } from "lucide-react";

export const Route = createFileRoute("/community/$communityId")({
  component: CommunityPage,
});

function CommunityPage() {
  const { communityId } = Route.useParams();
  const [alert, setAlert] = useState<Alert | null>(null);
  const [risk, setRisk] = useState<RiskCommunity | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      api.communityAlert(communityId),
      api.communityRisk(communityId),
    ])
      .then(([a, r]) => {
        if (a.status === "fulfilled") setAlert(a.value);
        if (r.status === "fulfilled") setRisk(r.value);
        if (a.status === "rejected" && r.status === "rejected") {
          setError("Community not found");
        }
      })
      .finally(() => setLoading(false));
  }, [communityId]);

  const name = alert?.community_name ?? risk?.community_name ?? communityId;

  return (
    <div className="min-h-screen bg-background">
      <SiteHeader />
      <main className="mx-auto max-w-4xl px-4 py-8">
        <Link
          to="/alerts"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back
        </Link>

        {loading ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading…
          </div>
        ) : error ? (
          <div className="mt-6 rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        ) : (
          <>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-bold text-foreground">{name}</h1>
              {alert && <LevelBadge level={alert.level} />}
            </div>
            {risk && (
              <p className="mt-1 text-sm text-muted-foreground">
                Corridor: {risk.corridor_id} · Data: {risk.data_quality}
              </p>
            )}

            {risk && (
              <section className="mt-6 rounded-lg border border-border bg-card p-6 shadow-[var(--shadow-card)]">
                <div className="flex items-baseline justify-between">
                  <h2 className="text-lg font-semibold text-card-foreground">
                    Risk score
                  </h2>
                  <span className="text-3xl font-bold tabular-nums text-foreground">
                    {risk.risk_score.toFixed(1)}
                    <span className="text-base text-muted-foreground">/100</span>
                  </span>
                </div>
                <div className="mt-3">
                  <RiskBar score={risk.risk_score} />
                </div>
                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  {Object.entries(risk.components).map(([k, v]) => (
                    <RiskBar
                      key={k}
                      score={v}
                      label={k.replace(/_/g, " ")}
                    />
                  ))}
                </div>
              </section>
            )}

            {alert && (
              <>
                <section className="mt-6 rounded-lg border border-border bg-card p-6">
                  <h2 className="text-lg font-semibold text-card-foreground">
                    {alert.headline}
                  </h2>
                  <p className="mt-3 whitespace-pre-line text-sm text-muted-foreground">
                    {alert.explanation}
                  </p>
                </section>

                {alert.recommended_actions?.length > 0 && (
                  <section className="mt-6 rounded-lg border border-border bg-card p-6">
                    <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-card-foreground">
                      <CheckSquare className="h-5 w-5 text-primary" />
                      Recommended actions
                    </h2>
                    <ul className="space-y-2">
                      {alert.recommended_actions.map((a, i) => (
                        <li
                          key={i}
                          className="flex gap-3 rounded-md bg-secondary p-3 text-sm text-secondary-foreground"
                        >
                          <span className="font-bold text-primary">{i + 1}.</span>
                          <span>{a}</span>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                <section className="mt-6 grid gap-4 sm:grid-cols-2">
                  <div className="rounded-lg border border-border bg-card p-5">
                    <h3 className="flex items-center gap-2 text-sm font-semibold text-card-foreground">
                      <MessageSquare className="h-4 w-4 text-primary" /> SMS body
                    </h3>
                    <p className="mt-2 rounded-md bg-muted p-3 font-mono text-xs text-foreground">
                      {alert.sms_body}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border bg-card p-5">
                    <h3 className="flex items-center gap-2 text-sm font-semibold text-card-foreground">
                      <Phone className="h-4 w-4 text-primary" /> Voice script
                    </h3>
                    <p className="mt-2 rounded-md bg-muted p-3 text-xs text-foreground">
                      {alert.voice_script}
                    </p>
                  </div>
                </section>
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}
