import { useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { US_STATES } from "@/data/states";
import { countyScore, getCountiesForState, stateAverageScore, useAppStore } from "@/store/appStore";
import { COMPONENT_WEIGHTS, TRIGGER_META, triggerForScore } from "@/lib/risk";
import { RiskBadge } from "@/components/RiskBadge";
import { Download, FileText } from "lucide-react";
import { format } from "date-fns";

const Transparency = () => {
  const [stateAbbr, setStateAbbr] = useState("IA");
  const counties = getCountiesForState(stateAbbr);
  const triggers = useAppStore((s) => s.triggers);

  const exportCsv = () => {
    const rows: string[][] = [["state", "county_fips", "county", "score", "trigger", "shock", "vulnerability", "supply", "readiness"]];
    US_STATES.forEach((s) => getCountiesForState(s.abbr).forEach((c) => {
      const cs = countyScore(c.fips)!;
      rows.push([s.abbr, c.fips, c.name, String(cs.total), cs.level, String(c.components.shockExposure), String(c.components.vulnerability), String(c.components.supplyCapacity), String(c.components.responseReadiness)]);
    }));
    const csv = rows.map((r) => r.map((x) => `"${x}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "foodready-scores.csv"; a.click();
  };

  return (
    <AppShell>
      <div className="space-y-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-3xl font-bold"><FileText className="h-6 w-6" /> Public transparency</h1>
            <p className="mt-1 text-sm text-muted-foreground">Read-only audit view: scores, methodology, trigger history, and recommendations.</p>
          </div>
          <Button onClick={exportCsv} variant="outline"><Download className="mr-1.5 h-4 w-4" /> Export CSV</Button>
        </div>

        <Card>
          <CardHeader><CardTitle className="text-base">Methodology</CardTitle></CardHeader>
          <CardContent className="text-sm text-muted-foreground space-y-2">
            <p>Food Access Risk Score (0–100, higher = more risk) = Shock {Math.round(COMPONENT_WEIGHTS.shockExposure*100)}% + Vulnerability {Math.round(COMPONENT_WEIGHTS.vulnerability*100)}% + Supply {Math.round(COMPONENT_WEIGHTS.supplyCapacity*100)}% + Readiness {Math.round(COMPONENT_WEIGHTS.responseReadiness*100)}%.</p>
            <p>Triggers: 0–39 Prepared · 40–59 Watch · 60–74 Warning · 75–89 Action · 90–100 Critical. Weights and thresholds are configurable in admin and should be calibrated against historical outcomes before production use.</p>
          </CardContent>
        </Card>

        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {US_STATES.slice(0, 10).map((s) => {
            const avg = stateAverageScore(s.abbr);
            return (
              <Card key={s.abbr}><CardContent className="p-4">
                <p className="text-xs uppercase text-muted-foreground">{s.abbr}</p>
                <p className="mt-0.5 text-sm font-medium">{s.name}</p>
                <div className="mt-2">{avg !== null ? <RiskBadge score={avg} /> : <span className="text-xs text-muted-foreground">no data</span>}</div>
              </CardContent></Card>
            );
          })}
        </div>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">County scores</CardTitle>
              <Select value={stateAbbr} onValueChange={setStateAbbr}>
                <SelectTrigger className="h-8 w-[200px] text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>{US_STATES.map((s) => <SelectItem key={s.abbr} value={s.abbr}>{s.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-hidden rounded border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                  <tr><th className="px-3 py-2 text-left">County</th><th className="px-3 py-2 text-right">Score</th><th className="px-3 py-2 text-right">Trigger</th></tr>
                </thead>
                <tbody>
                  {counties.map((c) => {
                    const cs = countyScore(c.fips)!;
                    return (
                      <tr key={c.fips} className="border-t">
                        <td className="px-3 py-2">{c.name}</td>
                        <td className="px-3 py-2 text-right tabular-nums font-semibold" style={{ color: TRIGGER_META[cs.level].color }}>{cs.total}</td>
                        <td className="px-3 py-2 text-right"><RiskBadge level={cs.level} /></td>
                      </tr>
                    );
                  })}
                  {counties.length === 0 && <tr><td colSpan={3} className="px-3 py-6 text-center text-sm text-muted-foreground">No seeded counties for this state.</td></tr>}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Trigger event history</CardTitle></CardHeader>
          <CardContent>
            <div className="overflow-hidden rounded border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                  <tr><th className="px-3 py-2 text-left">When</th><th className="px-3 py-2 text-left">State / County</th><th className="px-3 py-2 text-right">Score change</th><th className="px-3 py-2 text-right">Threshold</th><th className="px-3 py-2 text-left">Action</th><th className="px-3 py-2 text-right">Status</th></tr>
                </thead>
                <tbody>
                  {triggers.map((t) => (
                    <tr key={t.id} className="border-t">
                      <td className="px-3 py-2 text-xs text-muted-foreground">{format(new Date(t.timestamp), "PP")}</td>
                      <td className="px-3 py-2">{t.stateAbbr} · {t.countyFips}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{t.previousScore} → <strong>{t.newScore}</strong></td>
                      <td className="px-3 py-2 text-right"><RiskBadge level={t.thresholdCrossed} /></td>
                      <td className="px-3 py-2 text-xs">{t.recommendedAction}</td>
                      <td className="px-3 py-2 text-right text-xs capitalize">{t.actionStatus.replace(/_/g, " ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
};

export default Transparency;
