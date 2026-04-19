import { useMemo, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAppStore, getCountyByFips } from "@/store/appStore";
import { US_STATES } from "@/data/states";
import { toast } from "sonner";
import { AlertTriangle, ShieldCheck, Truck, Snowflake, DollarSign } from "lucide-react";
import { format, formatDistanceToNow } from "date-fns";
import type { RequestStatus, Urgency } from "@/types/foodready";

const urgencyOrder: Record<Urgency, number> = { urgent_24h: 0, moderate_week: 1, low_general: 2 };

const Responder = () => {
  const role = useAppStore((s) => s.role);
  const requests = useAppStore((s) => s.requests);
  const orgs = useAppStore((s) => s.organizations);
  const triggers = useAppStore((s) => s.triggers);
  const claim = useAppStore((s) => s.claimRequest);
  const resolve = useAppStore((s) => s.resolveRequest);
  const upsert = useAppStore((s) => s.upsertOrgCapacity);

  const [orgId, setOrgId] = useState(orgs[0]?.id ?? "");
  const [status, setStatus] = useState<RequestStatus | "all">("all");
  const [stateFilter, setStateFilter] = useState<string>("all");
  const [resolutionInputs, setResolutionInputs] = useState<Record<string, string>>({});

  const filtered = useMemo(() => {
    return requests
      .filter((r) => (status === "all" ? true : r.status === status))
      .filter((r) => (stateFilter === "all" ? true : r.stateAbbr === stateFilter))
      .sort((a, b) => urgencyOrder[a.urgency] - urgencyOrder[b.urgency] || +new Date(b.createdAt) - +new Date(a.createdAt));
  }, [requests, status, stateFilter]);

  const myOrg = orgs.find((o) => o.id === orgId);
  const myClaimed = requests.filter((r) => r.claimedBy === orgId);
  const myResolved = myClaimed.filter((r) => r.status === "resolved");
  const activeAlerts = triggers.filter((t) => ["action", "critical"].includes(t.thresholdCrossed));

  // Capacity form
  const [name, setName] = useState(myOrg?.name ?? "");
  const [stockLbs, setStockLbs] = useState(myOrg?.foodStockLbs ?? 0);
  const [vouchers, setVouchers] = useState(myOrg?.voucherCapacityUsd ?? 0);
  const [trucks, setTrucks] = useState(myOrg?.transportTrucks ?? 0);
  const [coldChain, setColdChain] = useState(myOrg?.coldChain ?? false);
  const [notes, setNotes] = useState(myOrg?.notes ?? "");

  const saveCapacity = () => {
    if (!myOrg) return;
    upsert({ ...myOrg, name: name || myOrg.name, foodStockLbs: Number(stockLbs), voucherCapacityUsd: Number(vouchers), transportTrucks: Number(trucks), coldChain, notes });
    toast.success("Capacity updated");
  };

  return (
    <AppShell>
      <div className="space-y-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold">Responder portal</h1>
            <p className="mt-1 text-sm text-muted-foreground">Triage requests, declare capacity, and track impact.</p>
          </div>
          <div className="flex items-center gap-2">
            <Label className="text-xs">Acting as</Label>
            <Select value={orgId} onValueChange={setOrgId}>
              <SelectTrigger className="h-8 w-[260px] text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>{orgs.map((o) => <SelectItem key={o.id} value={o.id}>{o.name}{!o.verified && " (unverified)"}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </div>

        {role === "public" && (
          <Card className="border-risk-watch/40 bg-risk-watch/5">
            <CardContent className="flex items-center gap-3 p-4 text-sm">
              <AlertTriangle className="h-4 w-4 text-risk-watch" />
              <p>You're viewing as <strong>Public</strong>. In production this portal requires verified responder login. Switch role to <strong>Responder</strong> in the top nav for the intended view.</p>
            </CardContent>
          </Card>
        )}

        {activeAlerts.length > 0 && (
          <Card className="border-risk-action/40 bg-risk-action/5">
            <CardContent className="p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-risk-action"><AlertTriangle className="h-4 w-4" /> Active alerts</div>
              <ul className="mt-2 space-y-1 text-sm">
                {activeAlerts.map((a) => {
                  const c = getCountyByFips(a.countyFips);
                  return (
                    <li key={a.id} className="flex items-center justify-between gap-2">
                      <span><strong>{c?.name}, {a.stateAbbr}</strong> · {a.recommendedAction}</span>
                      <span className="text-xs text-muted-foreground">{formatDistanceToNow(new Date(a.timestamp), { addSuffix: true })}</span>
                    </li>
                  );
                })}
              </ul>
            </CardContent>
          </Card>
        )}

        <Tabs defaultValue="feed">
          <TabsList>
            <TabsTrigger value="feed">Live request feed</TabsTrigger>
            <TabsTrigger value="capacity">Declare capacity</TabsTrigger>
            <TabsTrigger value="impact">Impact log</TabsTrigger>
          </TabsList>

          <TabsContent value="feed" className="mt-4 space-y-3">
            <div className="flex flex-wrap gap-2">
              {(["all", "open", "claimed", "resolved", "escalated"] as const).map((s) => (
                <Button key={s} size="sm" variant={status === s ? "secondary" : "ghost"} className="h-8 text-xs capitalize" onClick={() => setStatus(s)}>{s}</Button>
              ))}
              <div className="ml-auto">
                <Select value={stateFilter} onValueChange={setStateFilter}>
                  <SelectTrigger className="h-8 w-[180px] text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All states</SelectItem>
                    {US_STATES.map((s) => <SelectItem key={s.abbr} value={s.abbr}>{s.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              {filtered.length === 0 && <Card><CardContent className="p-6 text-center text-sm text-muted-foreground">No requests match the filters.</CardContent></Card>}
              {filtered.map((r) => {
                const county = getCountyByFips(r.countyFips);
                return (
                  <Card key={r.id}>
                    <CardContent className="p-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-xs text-muted-foreground">{r.reference}</span>
                            <Badge variant="outline" className="capitalize text-[10px]">{r.type.replace(/_/g, " ")}</Badge>
                            <Badge variant={r.urgency === "urgent_24h" ? "destructive" : "secondary"} className="text-[10px] capitalize">{r.urgency.replace(/_/g, " ")}</Badge>
                            <Badge className="text-[10px] capitalize">{r.status}</Badge>
                          </div>
                          <p className="mt-1.5 text-sm font-medium">{county?.name}, {r.stateAbbr} · {r.city || "—"} {r.zip}</p>
                          <p className="mt-1 text-sm text-muted-foreground">{r.description}</p>
                          {r.resolutionNote && <p className="mt-1 text-xs text-foreground/80"><strong>Update:</strong> {r.resolutionNote}</p>}
                        </div>
                        <div className="flex flex-col items-end gap-2 text-xs text-muted-foreground">
                          <span>{format(new Date(r.createdAt), "PP")}</span>
                          {r.householdSize > 0 && <span>{r.householdSize} people</span>}
                        </div>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {r.status === "open" && <Button size="sm" onClick={() => { claim(r.id, orgId); toast.success("Request claimed"); }}>Claim</Button>}
                        {r.status === "claimed" && r.claimedBy === orgId && (
                          <>
                            <Input
                              placeholder="Resolution note…"
                              value={resolutionInputs[r.id] ?? ""}
                              onChange={(e) => setResolutionInputs((p) => ({ ...p, [r.id]: e.target.value }))}
                              className="h-8 max-w-md text-xs"
                            />
                            <Button size="sm" variant="secondary" onClick={() => {
                              const note = resolutionInputs[r.id]?.trim() || "Resolved by responder.";
                              resolve(r.id, note); toast.success("Marked resolved");
                            }}>Mark resolved</Button>
                          </>
                        )}
                        {r.status === "claimed" && r.claimedBy !== orgId && <span className="text-xs text-muted-foreground">Claimed by another org</span>}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </TabsContent>

          <TabsContent value="capacity" className="mt-4">
            <Card className="mx-auto max-w-3xl">
              <CardHeader><CardTitle>Declare capacity</CardTitle></CardHeader>
              <CardContent>
                {!myOrg ? <p className="text-sm text-muted-foreground">Select a responder organization above.</p> : (
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="sm:col-span-2"><Label>Organization name</Label><Input value={name} onChange={(e) => setName(e.target.value)} /></div>
                    <div><Label className="flex items-center gap-1.5"><Truck className="h-3 w-3" /> Food stock (lbs)</Label><Input type="number" value={stockLbs} onChange={(e) => setStockLbs(Number(e.target.value))} /></div>
                    <div><Label className="flex items-center gap-1.5"><DollarSign className="h-3 w-3" /> Voucher capacity (USD)</Label><Input type="number" value={vouchers} onChange={(e) => setVouchers(Number(e.target.value))} /></div>
                    <div><Label className="flex items-center gap-1.5"><Truck className="h-3 w-3" /> Transport trucks</Label><Input type="number" value={trucks} onChange={(e) => setTrucks(Number(e.target.value))} /></div>
                    <div className="flex items-center gap-3 pt-6"><Switch checked={coldChain} onCheckedChange={setColdChain} id="cc" /><Label htmlFor="cc" className="flex items-center gap-1.5"><Snowflake className="h-3 w-3" /> Cold chain capable</Label></div>
                    <div className="sm:col-span-2"><Label>Notes</Label><Textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
                    <div className="sm:col-span-2 flex items-center justify-between">
                      <div className="text-xs text-muted-foreground">Last updated {formatDistanceToNow(new Date(myOrg.lastUpdated), { addSuffix: true })} · States: {myOrg.statesCovered.join(", ")}</div>
                      <Button onClick={saveCapacity}>Save capacity</Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="impact" className="mt-4 space-y-4">
            <div className="grid gap-3 sm:grid-cols-4">
              <Card><CardContent className="p-4"><p className="text-xs uppercase text-muted-foreground">Claimed</p><p className="mt-1 text-2xl font-bold">{myClaimed.length}</p></CardContent></Card>
              <Card><CardContent className="p-4"><p className="text-xs uppercase text-muted-foreground">Resolved</p><p className="mt-1 text-2xl font-bold text-risk-prepared">{myResolved.length}</p></CardContent></Card>
              <Card><CardContent className="p-4"><p className="text-xs uppercase text-muted-foreground">Resolution rate</p><p className="mt-1 text-2xl font-bold">{myClaimed.length === 0 ? "—" : `${Math.round((myResolved.length / myClaimed.length) * 100)}%`}</p></CardContent></Card>
              <Card><CardContent className="p-4"><p className="text-xs uppercase text-muted-foreground">Counties served</p><p className="mt-1 text-2xl font-bold">{myOrg?.countiesCovered.length ?? 0}</p></CardContent></Card>
            </div>
            <Card>
              <CardHeader><CardTitle className="text-base flex items-center gap-2"><ShieldCheck className="h-4 w-4" /> Donor / impact report</CardTitle></CardHeader>
              <CardContent>
                <Button variant="outline" onClick={() => {
                  const rows = [["reference", "state", "county", "type", "urgency", "status", "createdAt", "resolutionNote"], ...myClaimed.map((r) => [r.reference, r.stateAbbr, r.countyFips, r.type, r.urgency, r.status, r.createdAt, r.resolutionNote ?? ""])];
                  const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
                  const blob = new Blob([csv], { type: "text/csv" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a"); a.href = url; a.download = `foodready-impact-${orgId}.csv`; a.click();
                }}>Export CSV</Button>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
};

export default Responder;
