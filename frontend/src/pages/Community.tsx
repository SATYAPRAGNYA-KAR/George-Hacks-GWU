import { useMemo, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { US_STATES } from "@/data/states";
import { useAppStore, getCountiesForState } from "@/store/appStore";
import { toast } from "sonner";
import { CheckCircle2, Phone, MessageSquare, Search } from "lucide-react";
import { format } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { RequestType, Urgency } from "@/types/foodready";

const Community = () => {
  const addRequest = useAppStore((s) => s.addRequest);
  const addPriceReport = useAppStore((s) => s.addPriceReport);
  const requests = useAppStore((s) => s.requests);
  const orgs = useAppStore((s) => s.organizations);

  // Submit form state
  const [stateAbbr, setStateAbbr] = useState("IA");
  const [countyFips, setCountyFips] = useState("19007");
  const [city, setCity] = useState("");
  const [zip, setZip] = useState("");
  const [type, setType] = useState<RequestType>("household_food_shortage");
  const [urgency, setUrgency] = useState<Urgency>("moderate_week");
  const [householdSize, setHouseholdSize] = useState(1);
  const [description, setDescription] = useState("");
  const [contact, setContact] = useState("");
  const [submitted, setSubmitted] = useState<{ ref: string } | null>(null);

  // Status checker
  const [refLookup, setRefLookup] = useState("");
  const found = useMemo(() => requests.find((r) => r.reference.toLowerCase() === refLookup.trim().toLowerCase()), [refLookup, requests]);

  // Price form
  const [pState, setPState] = useState("IA");
  const [pCounty, setPCounty] = useState("19179");
  const [pStore, setPStore] = useState("");
  const [pItem, setPItem] = useState("");
  const [pPrice, setPPrice] = useState<number | "">("");
  const [pPkg, setPPkg] = useState("");
  const [pNote, setPNote] = useState("");

  const counties = getCountiesForState(stateAbbr);
  const pCounties = getCountiesForState(pState);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim() || description.length > 1000) return toast.error("Please add a short description (≤ 1000 chars).");
    const req = addRequest({
      stateAbbr, countyFips, city: city.trim().slice(0, 100), zip: zip.trim().slice(0, 10),
      type, urgency, householdSize: Math.max(0, Math.min(50, householdSize)),
      description: description.trim().slice(0, 1000), contact: contact.trim().slice(0, 120) || undefined,
    });
    setSubmitted({ ref: req.reference });
    toast.success(`Request submitted · Ref ${req.reference}`);
  };

  const submitPrice = (e: React.FormEvent) => {
    e.preventDefault();
    if (!pStore || !pItem || pPrice === "" || !pPkg) return toast.error("Please fill in store, item, price, and package size.");
    addPriceReport({
      stateAbbr: pState, countyFips: pCounty, storeName: pStore.slice(0, 120), date: format(new Date(), "yyyy-MM-dd"),
      item: pItem.slice(0, 80), price: Number(pPrice), packageSize: pPkg.slice(0, 40), note: pNote.slice(0, 240) || undefined,
    });
    setPStore(""); setPItem(""); setPPrice(""); setPPkg(""); setPNote("");
    toast.success("Price report saved");
  };

  return (
    <AppShell>
      <div className="space-y-5">
        <div>
          <h1 className="text-3xl font-bold">Community portal</h1>
          <p className="mt-1 text-sm text-muted-foreground">Submit a food access request, report a price spike, or check the status of an existing request. No login required.</p>
        </div>

        <Tabs defaultValue="submit">
          <TabsList>
            <TabsTrigger value="submit">Submit request</TabsTrigger>
            <TabsTrigger value="status">Check status</TabsTrigger>
            <TabsTrigger value="price">Report price</TabsTrigger>
            <TabsTrigger value="help">Get help</TabsTrigger>
          </TabsList>

          <TabsContent value="submit" className="mt-4">
            {submitted ? (
              <Card className="mx-auto max-w-xl">
                <CardContent className="space-y-3 p-8 text-center">
                  <CheckCircle2 className="mx-auto h-10 w-10 text-risk-prepared" />
                  <h2 className="text-xl font-bold">Request submitted</h2>
                  <p className="text-sm text-muted-foreground">Save this reference number to check status later.</p>
                  <div className="mx-auto inline-block rounded-lg bg-muted px-4 py-2 font-mono text-lg font-semibold">{submitted.ref}</div>
                  <div className="flex justify-center gap-2 pt-2">
                    <Button onClick={() => setSubmitted(null)}>Submit another</Button>
                    <Button variant="outline" onClick={() => { navigator.clipboard.writeText(submitted.ref); toast.success("Copied"); }}>Copy reference</Button>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <Card className="mx-auto max-w-3xl">
                <CardHeader><CardTitle>Submit a community request</CardTitle></CardHeader>
                <CardContent>
                  <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <Label>State</Label>
                      <Select value={stateAbbr} onValueChange={(v) => { setStateAbbr(v); setCountyFips(getCountiesForState(v)[0]?.fips ?? ""); }}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>{US_STATES.map((s) => <SelectItem key={s.abbr} value={s.abbr}>{s.name}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label>County</Label>
                      <Select value={countyFips} onValueChange={setCountyFips} disabled={counties.length === 0}>
                        <SelectTrigger><SelectValue placeholder={counties.length === 0 ? "No seeded counties" : ""} /></SelectTrigger>
                        <SelectContent>{counties.map((c) => <SelectItem key={c.fips} value={c.fips}>{c.name}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div><Label>City / town</Label><Input value={city} onChange={(e) => setCity(e.target.value)} maxLength={100} /></div>
                    <div><Label>ZIP</Label><Input value={zip} onChange={(e) => setZip(e.target.value)} maxLength={10} /></div>
                    <div>
                      <Label>Type of need</Label>
                      <Select value={type} onValueChange={(v) => setType(v as RequestType)}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="household_food_shortage">Household food shortage</SelectItem>
                          <SelectItem value="pantry_low_stock">Pantry low stock</SelectItem>
                          <SelectItem value="market_price_spike">Market price spike</SelectItem>
                          <SelectItem value="responder_capacity_gap">Responder capacity gap</SelectItem>
                          <SelectItem value="transportation_access_issue">Transportation/access issue</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label>Urgency</Label>
                      <Select value={urgency} onValueChange={(v) => setUrgency(v as Urgency)}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="urgent_24h">Urgent — within 24 hours</SelectItem>
                          <SelectItem value="moderate_week">Moderate — within a week</SelectItem>
                          <SelectItem value="low_general">Low / general shortage</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div><Label>People affected</Label><Input type="number" min={0} max={50} value={householdSize} onChange={(e) => setHouseholdSize(Number(e.target.value))} /></div>
                    <div><Label>Contact (optional)</Label><Input value={contact} onChange={(e) => setContact(e.target.value)} maxLength={120} placeholder="Phone or email" /></div>
                    <div className="sm:col-span-2"><Label>Description</Label><Textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={1000} rows={4} placeholder="Briefly describe the situation…" /></div>
                    <div className="sm:col-span-2 flex justify-end"><Button type="submit">Submit request</Button></div>
                  </form>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="status" className="mt-4">
            <Card className="mx-auto max-w-2xl">
              <CardHeader><CardTitle>Check request status</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="flex gap-2">
                  <div className="relative flex-1"><Search className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" /><Input value={refLookup} onChange={(e) => setRefLookup(e.target.value)} placeholder="FR-XXXX-XXXX" className="pl-8 font-mono" /></div>
                  <Button onClick={() => setRefLookup(refLookup)}>Look up</Button>
                </div>
                {refLookup && (found ? (
                  <div className="rounded-lg border bg-card p-4">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <p className="font-mono font-semibold">{found.reference}</p>
                        <p className="text-xs text-muted-foreground">Submitted {format(new Date(found.createdAt), "PP")}</p>
                      </div>
                      <Badge variant="secondary" className="capitalize">{found.status}</Badge>
                    </div>
                    <div className="mt-3 grid gap-1 text-sm">
                      <div><span className="text-muted-foreground">Location: </span>{found.city}, {found.stateAbbr} {found.zip}</div>
                      <div><span className="text-muted-foreground">Type: </span>{found.type.replace(/_/g, " ")}</div>
                      <div><span className="text-muted-foreground">Urgency: </span>{found.urgency.replace(/_/g, " ")}</div>
                      {found.resolutionNote && <div><span className="text-muted-foreground">Latest update: </span>{found.resolutionNote}</div>}
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No request found with that reference.</p>
                ))}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="price" className="mt-4">
            <Card className="mx-auto max-w-3xl">
              <CardHeader><CardTitle>Report a price</CardTitle></CardHeader>
              <CardContent>
                <form onSubmit={submitPrice} className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <Label>State</Label>
                    <Select value={pState} onValueChange={(v) => { setPState(v); setPCounty(getCountiesForState(v)[0]?.fips ?? ""); }}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>{US_STATES.map((s) => <SelectItem key={s.abbr} value={s.abbr}>{s.name}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>County</Label>
                    <Select value={pCounty} onValueChange={setPCounty} disabled={pCounties.length === 0}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>{pCounties.map((c) => <SelectItem key={c.fips} value={c.fips}>{c.name}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div><Label>Store / market</Label><Input value={pStore} onChange={(e) => setPStore(e.target.value)} /></div>
                  <div><Label>Item</Label><Input value={pItem} onChange={(e) => setPItem(e.target.value)} placeholder="Eggs, milk, bread…" /></div>
                  <div><Label>Price (USD)</Label><Input type="number" step="0.01" value={pPrice} onChange={(e) => setPPrice(e.target.value === "" ? "" : Number(e.target.value))} /></div>
                  <div><Label>Package size</Label><Input value={pPkg} onChange={(e) => setPPkg(e.target.value)} placeholder="dozen, gallon, 1 lb" /></div>
                  <div className="sm:col-span-2"><Label>Note (optional)</Label><Textarea rows={3} value={pNote} onChange={(e) => setPNote(e.target.value)} maxLength={240} /></div>
                  <div className="sm:col-span-2 flex justify-end"><Button type="submit">Submit price</Button></div>
                </form>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="help" className="mt-4 space-y-4">
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2 text-base"><MessageSquare className="h-4 w-4" /> SMS fallback (placeholder)</CardTitle></CardHeader>
              <CardContent className="text-sm text-muted-foreground">In production, text <strong className="text-foreground">FOOD</strong> to <strong className="font-mono text-foreground">+1-555-FOODRDY</strong>. SMS gateway is integration-ready.</CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-base">Active responders</CardTitle></CardHeader>
              <CardContent>
                <ul className="divide-y">
                  {orgs.filter((o) => o.verified).map((o) => (
                    <li key={o.id} className="flex items-center justify-between py-2 text-sm">
                      <div>
                        <p className="font-medium">{o.name}</p>
                        <p className="text-xs text-muted-foreground">{o.statesCovered.join(", ")} · {o.countiesCovered.length} counties</p>
                      </div>
                      <Phone className="h-4 w-4 text-muted-foreground" />
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
};

export default Community;
