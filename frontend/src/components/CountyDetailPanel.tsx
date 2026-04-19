import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { RiskBadge, RiskScore } from "@/components/RiskBadge";
import { TrendChart } from "@/components/charts/Charts";
import { COMPONENT_WEIGHTS, TRIGGER_META, computeTotalScore, triggerForScore } from "@/lib/risk";
import {
  countyScore, generateTrend, getCountyByFips, recommendationsForCounty, useAppStore,
} from "@/store/appStore";
import { Activity, AlertTriangle, Boxes, HeartHandshake, Sparkles, Truck, Users } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

export const CountyDetailPanel = ({ fips }: { fips: string }) => {
  const county = getCountyByFips(fips);
  const requests = useAppStore((s) => s.requests.filter((r) => r.countyFips === fips));
  const orgs = useAppStore((s) => s.organizations.filter((o) => o.countiesCovered.includes(fips)));
  const triggers = useAppStore((s) => s.triggers.filter((t) => t.countyFips === fips));
  const weights = useAppStore((s) => s.weights);

  if (!county) {
    return <Card><CardContent className="p-6 text-sm text-muted-foreground">Select a county on the map to view details.</CardContent></Card>;
  }
  const total = computeTotalScore(county.components, weights);
  const level = triggerForScore(total);
  const meta = TRIGGER_META[level];
  const trend = generateTrend(fips, 14);
  const recs = recommendationsForCounty(fips, weights);
  const drivers = (county as any).drivers ?? [];
  const totalStock = orgs.reduce((s, o) => s + o.foodStockLbs, 0);
  const totalVouchers = orgs.reduce((s, o) => s + o.voucherCapacityUsd, 0);

  const components = [
    { label: "Shock exposure", value: county.components.shockExposure, weight: weights.shockExposure, icon: AlertTriangle },
    { label: "Vulnerability", value: county.components.vulnerability, weight: weights.vulnerability, icon: Users },
    { label: "Supply capacity", value: county.components.supplyCapacity, weight: weights.supplyCapacity, icon: Boxes },
    { label: "Response readiness", value: county.components.responseReadiness, weight: weights.responseReadiness, icon: Truck },
  ];

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b bg-gradient-card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">{county.stateAbbr} · {county.fips}</p>
            <CardTitle className="mt-0.5 text-2xl">{county.name} County</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">Population {county.population.toLocaleString()} · Updated {formatDistanceToNow(new Date(), { addSuffix: true })}</p>
          </div>
          <div className="text-right">
            <RiskScore score={total} />
            <div className="mt-1.5"><RiskBadge level={level} /></div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6 p-5">
        <section>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">14-day risk trend</h4>
          <TrendChart data={trend} height={140} />
        </section>

        <section>
          <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Component scores</h4>
          <div className="grid grid-cols-2 gap-3">
            {components.map((c) => (
              <div key={c.label} className="rounded-lg border bg-background/60 p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground"><c.icon className="h-3 w-3" />{c.label}</div>
                  <Badge variant="outline" className="text-[10px]">{Math.round(c.weight * 100)}%</Badge>
                </div>
                <div className="mt-1.5 flex items-baseline gap-1.5">
                  <span className="text-xl font-bold tabular-nums" style={{ color: TRIGGER_META[triggerForScore(c.value)].color }}>{c.value}</span>
                  <span className="text-[10px] text-muted-foreground">/100</span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full" style={{ width: `${c.value}%`, backgroundColor: TRIGGER_META[triggerForScore(c.value)].color }} />
                </div>
              </div>
            ))}
          </div>
        </section>

        {drivers.length > 0 && (
          <section>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Top signal drivers</h4>
            <div className="space-y-1.5">
              {drivers.map((d: any, i: number) => (
                <div key={i} className="flex items-center justify-between rounded-md border bg-background/60 px-3 py-1.5 text-xs">
                  <span>{d.label}</span>
                  <span className="font-mono tabular-nums" style={{ color: TRIGGER_META[triggerForScore(d.value)].color }}>{d.value}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        <section>
          <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground"><Sparkles className="h-3 w-3" /> Recommended actions</h4>
          <div className="space-y-2">
            {recs.length === 0 ? <p className="text-xs text-muted-foreground">No actions recommended.</p> : recs.map((r) => (
              <div key={r.id} className="rounded-lg border bg-accent/30 p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium">{r.text}</p>
                  <RiskBadge level={r.urgency} />
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{r.reason}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                  <span>Timeline: <strong className="text-foreground">{r.timeline}</strong></span>
                  <span>·</span>
                  <span>Confidence: <strong className="text-foreground">{r.confidence}</strong></span>
                  <span>·</span>
                  <span>Signals: {r.signalsUsed.join(", ")}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="grid grid-cols-2 gap-3">
          <div className="rounded-lg border bg-background/60 p-3">
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground"><Activity className="h-3 w-3" />Open requests</div>
            <p className="mt-1 text-2xl font-bold tabular-nums">{requests.filter((r) => r.status !== "resolved").length}</p>
            <p className="text-[10px] text-muted-foreground">{requests.length} total in this county</p>
          </div>
          <div className="rounded-lg border bg-background/60 p-3">
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground"><HeartHandshake className="h-3 w-3" />Responder capacity</div>
            <p className="mt-1 text-2xl font-bold tabular-nums">{(totalStock / 1000).toFixed(0)}k lbs</p>
            <p className="text-[10px] text-muted-foreground">${totalVouchers.toLocaleString()} vouchers · {orgs.length} orgs</p>
          </div>
        </section>

        {triggers.length > 0 && (
          <section>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Recent trigger events</h4>
            <div className="space-y-1.5">
              {triggers.slice(0, 3).map((t) => (
                <div key={t.id} className="flex items-center justify-between rounded-md border bg-background/60 px-3 py-1.5 text-xs">
                  <div className="flex items-center gap-2">
                    <RiskBadge level={t.thresholdCrossed} />
                    <span className="text-muted-foreground">{t.previousScore} → {t.newScore}</span>
                  </div>
                  <span className="text-muted-foreground">{formatDistanceToNow(new Date(t.timestamp), { addSuffix: true })}</span>
                </div>
              ))}
            </div>
          </section>
        )}
      </CardContent>
    </Card>
  );
};
