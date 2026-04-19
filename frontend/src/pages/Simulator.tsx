import { useMemo, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { US_STATES } from "@/data/states";
import { getCountiesForState, useAppStore } from "@/store/appStore";
import { computeTotalScore, triggerForScore, TRIGGER_META } from "@/lib/risk";
import { RiskBadge } from "@/components/RiskBadge";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { FlaskConical } from "lucide-react";

const SCENARIOS = [
  "Severe storm / tornado", "Flood", "Drought", "Blizzard / winter storm",
  "Derecho", "Freeze", "Heat wave", "Wildfire smoke / disruption",
];

const Simulator = () => {
  const [params] = useSearchParams();
  const [stateAbbr, setStateAbbr] = useState(params.get("state") ?? "IA");
  const [scenario, setScenario] = useState(SCENARIOS[1]);
  const [shock, setShock] = useState(20);          // adds to shock exposure
  const [supply, setSupply] = useState(15);        // adds to supply gap
  const [readiness, setReadiness] = useState(10);  // adds to readiness gap
  const [vuln, setVuln] = useState(5);             // adds to vulnerability
  const addScenario = useAppStore((s) => s.addScenario);

  const counties = getCountiesForState(stateAbbr);

  const sim = useMemo(() => {
    return counties.map((c) => {
      const before = computeTotalScore(c.components);
      const after = computeTotalScore({
        shockExposure: Math.min(100, c.components.shockExposure + shock),
        vulnerability: Math.min(100, c.components.vulnerability + vuln),
        supplyCapacity: Math.min(100, c.components.supplyCapacity + supply),
        responseReadiness: Math.min(100, c.components.responseReadiness + readiness),
      });
      return { fips: c.fips, name: c.name, before, after, level: triggerForScore(after) };
    }).sort((a, b) => (b.after - b.before) - (a.after - a.before));
  }, [counties, shock, supply, readiness, vuln]);

  const beforeAvg = sim.length ? Math.round((sim.reduce((s, x) => s + x.before, 0) / sim.length) * 10) / 10 : 0;
  const afterAvg = sim.length ? Math.round((sim.reduce((s, x) => s + x.after, 0) / sim.length) * 10) / 10 : 0;

  const save = () => {
    addScenario({
      stateAbbr, scenario,
      inputs: { shock, supply, readiness, vuln },
      beforeAvg, afterAvg,
      affectedCounties: sim.map((s) => ({ fips: s.fips, before: s.before, after: s.after, level: s.level })),
    });
    toast.success("Scenario saved to log");
  };

  return (
    <AppShell>
      <div className="space-y-5">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-bold"><FlaskConical className="h-6 w-6" /> Scenario simulator</h1>
          <p className="mt-1 text-sm text-muted-foreground">Stress-test county scores under hypothetical shocks. Saved to scenario log.</p>
        </div>

        <div className="grid gap-5 lg:grid-cols-3">
          <Card className="lg:col-span-1">
            <CardHeader><CardTitle className="text-base">Inputs</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>State</Label>
                <Select value={stateAbbr} onValueChange={setStateAbbr}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{US_STATES.map((s) => <SelectItem key={s.abbr} value={s.abbr}>{s.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label>Scenario</Label>
                <Select value={scenario} onValueChange={setScenario}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{SCENARIOS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              {[
                { label: "Shock exposure +", val: shock, set: setShock },
                { label: "Supply capacity gap +", val: supply, set: setSupply },
                { label: "Response readiness gap +", val: readiness, set: setReadiness },
                { label: "Vulnerability +", val: vuln, set: setVuln },
              ].map((s) => (
                <div key={s.label}>
                  <div className="flex items-center justify-between"><Label className="text-xs">{s.label}</Label><span className="text-xs font-mono">{s.val}</span></div>
                  <Slider value={[s.val]} onValueChange={(v) => s.set(v[0])} min={0} max={50} step={1} className="mt-2" />
                </div>
              ))}
              <Button onClick={save} className="w-full">Save scenario to log</Button>
            </CardContent>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Result</CardTitle>
              <p className="text-xs text-muted-foreground">State avg: <strong>{beforeAvg}</strong> → <strong style={{ color: TRIGGER_META[triggerForScore(afterAvg)].color }}>{afterAvg}</strong> ({afterAvg - beforeAvg >= 0 ? "+" : ""}{(afterAvg - beforeAvg).toFixed(1)})</p>
            </CardHeader>
            <CardContent>
              {sim.length === 0 ? <p className="text-sm text-muted-foreground">No counties seeded for this state.</p> : (
                <div className="overflow-hidden rounded border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                      <tr><th className="px-3 py-2 text-left">County</th><th className="px-3 py-2 text-right">Before</th><th className="px-3 py-2 text-right">After</th><th className="px-3 py-2 text-right">Δ</th><th className="px-3 py-2 text-right">Trigger</th></tr>
                    </thead>
                    <tbody>
                      {sim.map((r) => (
                        <tr key={r.fips} className="border-t">
                          <td className="px-3 py-2 font-medium">{r.name}</td>
                          <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">{r.before}</td>
                          <td className="px-3 py-2 text-right tabular-nums font-semibold" style={{ color: TRIGGER_META[r.level].color }}>{r.after}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{r.after - r.before >= 0 ? "+" : ""}{(r.after - r.before).toFixed(1)}</td>
                          <td className="px-3 py-2 text-right"><RiskBadge level={r.level} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
};

export default Simulator;
