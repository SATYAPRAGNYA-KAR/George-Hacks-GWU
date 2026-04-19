import { useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { useAppStore } from "@/store/appStore";
import { COMPONENT_WEIGHTS } from "@/lib/risk";
import { toast } from "sonner";
import { AlertTriangle, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const Admin = () => {
  const role = useAppStore((s) => s.role);
  const weights = useAppStore((s) => s.weights);
  const setWeights = useAppStore((s) => s.setWeights);
  const thresholds = useAppStore((s) => s.thresholds);
  const setThresholds = useAppStore((s) => s.setThresholds);
  const orgs = useAppStore((s) => s.organizations);
  const verifyOrg = useAppStore((s) => s.verifyOrg);

  const [w, setW] = useState(weights);
  const [t, setT] = useState(thresholds);

  const total = Math.round((w.shockExposure + w.vulnerability + w.supplyCapacity + w.responseReadiness) * 100);
  const balanced = total === 100;

  return (
    <AppShell>
      <div className="space-y-5">
        <div>
          <h1 className="text-3xl font-bold">Admin settings</h1>
          <p className="mt-1 text-sm text-muted-foreground">Tune model weights, trigger thresholds, and manage responder verification.</p>
        </div>

        {role !== "admin" && (
          <Card className="border-risk-watch/40 bg-risk-watch/5">
            <CardContent className="flex items-center gap-2 p-4 text-sm">
              <AlertTriangle className="h-4 w-4 text-risk-watch" />
              In production this requires <strong>admin</strong> login. Switch your role in the top nav.
            </CardContent>
          </Card>
        )}

        <Card className="border-amber-500/30 bg-amber-500/5">
          <CardContent className="p-4 text-xs text-amber-900 dark:text-amber-200">
            ⚠ Weights and thresholds are configurable but should be calibrated against historical outcomes before production use.
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Component weights · must sum to 100%</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {([
              ["Shock exposure", "shockExposure"],
              ["Vulnerability", "vulnerability"],
              ["Supply capacity", "supplyCapacity"],
              ["Response readiness", "responseReadiness"],
            ] as const).map(([label, key]) => (
              <div key={key}>
                <div className="flex items-center justify-between"><Label>{label}</Label><span className="text-xs font-mono">{Math.round((w as any)[key] * 100)}%</span></div>
                <Slider value={[(w as any)[key] * 100]} onValueChange={(v) => setW({ ...w, [key]: v[0] / 100 })} min={0} max={100} step={5} className="mt-2" />
              </div>
            ))}
            <div className="flex items-center justify-between border-t pt-3">
              <div className="text-sm">Total: <strong className={balanced ? "text-risk-prepared" : "text-risk-action"}>{total}%</strong></div>
              <div className="flex gap-2">
                <Button variant="ghost" onClick={() => setW(COMPONENT_WEIGHTS)}>Reset</Button>
                <Button disabled={!balanced} onClick={() => { setWeights(w); toast.success("Weights saved"); }}>Save weights</Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Trigger thresholds</CardTitle></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-4">
            {(["watch", "warning", "action", "critical"] as const).map((k) => (
              <div key={k}>
                <Label className="capitalize">{k}</Label>
                <Input type="number" min={0} max={100} value={(t as any)[k]} onChange={(e) => setT({ ...t, [k]: Number(e.target.value) })} />
              </div>
            ))}
            <div className="sm:col-span-4 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setT({ watch: 40, warning: 60, action: 75, critical: 90 })}>Reset</Button>
              <Button onClick={() => { setThresholds(t); toast.success("Thresholds saved"); }}>Save thresholds</Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2 text-base"><ShieldCheck className="h-4 w-4" /> Responder verification</CardTitle></CardHeader>
          <CardContent>
            <ul className="divide-y">
              {orgs.map((o) => (
                <li key={o.id} className="flex items-center justify-between py-2.5">
                  <div>
                    <p className="text-sm font-medium">{o.name}</p>
                    <p className="text-xs text-muted-foreground capitalize">{o.type.replace(/_/g, " ")} · {o.statesCovered.join(", ")}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {o.verified ? <Badge variant="secondary">Verified</Badge> : <Button size="sm" onClick={() => { verifyOrg(o.id); toast.success("Verified"); }}>Verify</Button>}
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
};

export default Admin;
