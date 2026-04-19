import { useMemo, useState, useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { StateCountyMap } from "@/components/maps/StateCountyMap";
import { CountyDetailPanel } from "@/components/CountyDetailPanel";
import { MetricCard, MetricStrip } from "@/components/MetricCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { RiskBadge } from "@/components/RiskBadge";
import { Badge } from "@/components/ui/badge";
import {
  ChevronLeft, Search, AlertTriangle, BarChart3, Users,
  Activity, Cloud, Droplets, Wind, RefreshCw, Wifi, WifiOff, Flame
} from "lucide-react";
import { STATE_BY_ABBR } from "@/data/states";
import { countyScore, getCountiesForState, stateAverageScore, useAppStore } from "@/store/appStore";
import { triggerForScore, TRIGGER_META } from "@/lib/risk";
import { ScoreBarChart } from "@/components/charts/Charts";
import {
  fetchStateFPI,
  fetchWeather,
  fetchCountyFPI,
  type StateFPIDetail,
  type WeatherSnapshot,
  type CountyFPIDetail,
} from "@/lib/api";

const TRIGGER_COLOR: Record<string, string> = {
  prepared: "text-emerald-600", watch: "text-yellow-600",
  warning: "text-orange-500", action: "text-red-500", critical: "text-red-700",
};

// const DroughtBadge = ({ cls }: { cls: string }) => {
//   const colors: Record<string, string> = {
//     None: "bg-emerald-100 text-emerald-700",
//     D0: "bg-yellow-100 text-yellow-700", D1: "bg-orange-100 text-orange-700",
//     D2: "bg-orange-200 text-orange-800", D3: "bg-red-200 text-red-800",
//     D4: "bg-red-300 text-red-900", unknown: "bg-muted text-muted-foreground",
//   };
//   return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${colors[cls] ?? colors.unknown}`}>{cls === "None" ? "No drought" : cls}</span>;
// };
const DroughtBadge = ({ cls }: { cls: string }) => {
  const colors: Record<string, string> = {
    None:    "bg-emerald-100 text-emerald-700",  // ← add this
    D0: "bg-yellow-100 text-yellow-700",
    D1: "bg-orange-100 text-orange-700",
    D2: "bg-orange-200 text-orange-800",
    D3: "bg-red-200 text-red-800",
    D4: "bg-red-300 text-red-900",
    unknown: "bg-muted text-muted-foreground",
  };
  const label = cls === "None" ? "No drought" : cls === "unknown" ? "No data" : cls;
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${colors[cls] ?? colors.unknown}`}>
      {label}
    </span>
  );
};

const WeatherStrip = ({ weather }: { weather: WeatherSnapshot }) => (
  <Card>
    <CardHeader className="pb-2">
      <CardTitle className="flex items-center gap-2 text-sm">
        <Cloud className="h-4 w-4" /> Live weather conditions
        <span className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-medium ${
          weather.overall_status === "blocked" ? "bg-red-100 text-red-700" :
          weather.overall_status === "impaired" ? "bg-orange-100 text-orange-700" :
          "bg-emerald-100 text-emerald-700"
        }`}>{weather.overall_status.toUpperCase()}</span>
      </CardTitle>
    </CardHeader>
    <CardContent className="space-y-3 text-xs">
      <div className="flex items-center gap-3">
        <Droplets className="h-3.5 w-3.5 text-blue-500 shrink-0" />
        <span className="text-muted-foreground">Drought</span>
        <DroughtBadge cls={weather.drought?.max_class ?? "unknown"} />
        {weather.drought?.d2_pct > 10 && (
          <span className="text-muted-foreground">{weather.drought.d2_pct.toFixed(0)}% in D2+</span>
        )}
      </div>
      {weather.active_storms?.length > 0 && (
        <div className="flex items-center gap-2 text-orange-700">
          <Wind className="h-3.5 w-3.5" />
          <span>{weather.active_storms.length} active storm track(s)</span>
        </div>
      )}
      {weather.firms_anomalies?.length > 0 && (
        <div className="flex items-center gap-2 text-red-600">
          <Flame className="h-3.5 w-3.5" />
          <span>{weather.firms_anomalies.length} NASA FIRMS thermal anomalies</span>
        </div>
      )}
      {weather.nws_alerts?.length > 0 ? (
        <div className="space-y-1">
          {weather.nws_alerts.slice(0, 3).map((a, i) => (
            <div key={i} className="flex items-start gap-2">
              <AlertTriangle className="h-3 w-3 mt-0.5 text-orange-500 shrink-0" />
              <span className="text-muted-foreground">{a.event} ({a.severity})</span>
            </div>
          ))}
          {weather.nws_alerts.length > 3 && (
            <span className="text-muted-foreground">+{weather.nws_alerts.length - 3} more alerts</span>
          )}
        </div>
      ) : (
        <p className="text-muted-foreground">No active NWS alerts</p>
      )}
    </CardContent>
  </Card>
);

const GeminiWeightsCard = ({ fpi }: { fpi: StateFPIDetail }) => {
  const weights = fpi.state_weights ?? {};
  const entries = Object.entries(weights).sort((a, b) => b[1] - a[1]);
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">
          Gemini weight analysis
          <span className={`ml-2 text-[10px] font-normal ${fpi.gemini_source === "gemini" ? "text-emerald-600" : "text-muted-foreground"}`}>
            {fpi.gemini_source === "gemini" ? "● Live" : "● Baseline"}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs">
        {fpi.reasoning && (
          <p className="text-muted-foreground italic border-l-2 border-muted pl-2">{fpi.reasoning}</p>
        )}
        <div className="space-y-1.5 mt-2">
          {entries.map(([k, v]) => (
            <div key={k} className="flex items-center gap-2">
              <span className="w-36 shrink-0 text-muted-foreground capitalize">{k.replace(/_/g, " ")}</span>
              <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                <div className="h-full rounded-full bg-primary" style={{ width: `${Math.round(v * 100)}%` }} />
              </div>
              <span className="w-8 text-right font-mono">{Math.round(v * 100)}%</span>
            </div>
          ))}
        </div>
        {fpi.recommended_actions?.length > 0 && (
          <div className="mt-3 space-y-1">
            <p className="font-medium text-foreground">Recommended actions</p>
            {fpi.recommended_actions.map((a, i) => (
              <p key={i} className="text-muted-foreground">· {a}</p>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};


const StateDashboard = () => {
  const { stateAbbr = "IA" } = useParams();
  const stateInfo = STATE_BY_ABBR[stateAbbr];
  const counties  = getCountiesForState(stateAbbr);
  const requests  = useAppStore((s) => s.requests.filter((r) => r.stateAbbr === stateAbbr));
  const triggers  = useAppStore((s) => s.triggers.filter((t) => t.stateAbbr === stateAbbr));

  const [selected, setSelected] = useState<string | undefined>(counties[0]?.fips);
  const [q, setQ] = useState("");
  const [trig, setTrig] = useState<string>("all");

  // Reset selected county when state changes
  useEffect(() => {
    setSelected(counties[0]?.fips);
  }, [stateAbbr]);

  // Live backend: state FPI
  const { data: stateFPI, isLoading: fpiLoading, isError: fpiError, refetch } = useQuery({
    queryKey: ["state-fpi", stateAbbr],
    queryFn: () => fetchStateFPI(stateAbbr),
    staleTime: 5 * 60_000,
    retry: 1,
    enabled: !!stateAbbr,
  });

  // Live backend: weather snapshot
  const { data: weather } = useQuery({
    queryKey: ["weather", stateAbbr],
    queryFn: () => fetchWeather(stateAbbr),
    staleTime: 5 * 60_000,
    retry: 1,
    enabled: !!stateAbbr,
  });

  // Live backend: county FPI for selected county
  const selectedCounty = counties.find((c) => c.fips === selected);
  const { data: countyFPI } = useQuery({
    queryKey: ["county-fpi", stateAbbr, selected],
    queryFn: () => fetchCountyFPI(stateAbbr, selected!, selectedCounty?.name ?? ""),
    staleTime: 5 * 60_000,
    retry: 1,
    enabled: !!selected,
  });

  // Blend live + baseline scores
  const avg    = stateFPI?.risk_score ?? stateAverageScore(stateAbbr) ?? 0;
  const alerts = triggers.filter((t) => ["warning", "action", "critical"].includes(t.thresholdCrossed)).length
    + (stateFPI && ["warning","action","critical"].includes(stateFPI.trigger) ? 1 : 0);

  // const ranking = useMemo(() => {
  //   return counties.map((c) => {
  //     const cs   = countyScore(c.fips)!;
  //     return { fips: c.fips, name: c.name, total: cs?.total ?? 30, level: cs?.level ?? "prepared", pop: c.population };
  //   })
  //     .filter((r) => r.name.toLowerCase().includes(q.toLowerCase()))
  //     .filter((r) => trig === "all" ? true : r.level === trig)
  //     .sort((a, b) => b.total - a.total);
  // }, [counties, q, trig]);
  const ranking = useMemo(() => {
    return counties.map((c) => {
      const cs = countyScore(c.fips);
      // Prefer live backend score if available for this county
      // (populated when user clicks a county and the query runs)
      const backendScore = countyFPI?.county_fips === c.fips
        ? countyFPI.risk_score
        : null;
      const total = backendScore ?? cs?.total ?? 30;
      const level = backendScore
        ? countyFPI!.trigger
        : cs?.level ?? "prepared";
      return { fips: c.fips, name: c.name, total, level, pop: c.population };
    })
      .filter((r) => r.name.toLowerCase().includes(q.toLowerCase()))
      .filter((r) => trig === "all" ? true : r.level === trig)
      .sort((a, b) => b.total - a.total);
  }, [counties, q, trig, countyFPI]);

  if (!stateInfo) {
    return <AppShell><Card><CardContent className="p-6">Unknown state.</CardContent></Card></AppShell>;
  }

  return (
    <AppShell>
      <div className="space-y-5">
        <div>
          <Link to="/dashboard" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            <ChevronLeft className="h-3 w-3" /> United States
          </Link>
          <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-3xl font-bold">
                {stateInfo.name}{" "}
                <span className="text-base font-normal text-muted-foreground">({stateInfo.abbr})</span>
              </h1>
              <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                {fpiLoading && <span className="flex items-center gap-1"><RefreshCw className="h-3 w-3 animate-spin" /> Loading live data…</span>}
                {!fpiLoading && !fpiError && stateFPI && (
                  <span className="flex items-center gap-1 text-emerald-600"><Wifi className="h-3 w-3" /> Live · Gemini · NOAA</span>
                )}
                {!fpiLoading && fpiError && (
                  <span className="flex items-center gap-1 text-yellow-600"><WifiOff className="h-3 w-3" /> Baseline data</span>
                )}
              </div>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => refetch()} className="h-8 text-xs gap-1">
                <RefreshCw className="h-3 w-3" /> Refresh
              </Button>
              <Button asChild variant="outline" size="sm">
                <Link to={`/simulator?state=${stateAbbr}`}>Run scenario →</Link>
              </Button>
            </div>
          </div>
        </div>

        <MetricStrip>
          <MetricCard label="Counties monitored" value={counties.length} icon={<BarChart3 className="h-4 w-4" />} />
          <MetricCard label="Active alerts" value={alerts} icon={<AlertTriangle className="h-4 w-4" />} accent="text-risk-action" />
          <MetricCard label="Open requests" value={requests.filter((r) => r.status !== "resolved").length}
            hint={`${requests.length} total`} icon={<Users className="h-4 w-4" />} />
          <MetricCard label="State risk score" value={Math.round(avg)}
            hint={stateFPI ? TRIGGER_META[stateFPI.trigger as any]?.label ?? "" : TRIGGER_META[triggerForScore(avg)]?.label ?? ""}
            icon={<Activity className="h-4 w-4" />}
            accent={stateFPI ? (TRIGGER_COLOR[stateFPI.trigger] ?? "") : ""} />
          {weather && (
            <MetricCard label="Shock score" value={Math.round(weather.shock_score)}
              hint={weather.overall_status} icon={<Cloud className="h-4 w-4" />} />
          )}
        </MetricStrip>

        {/* Live FPI + Gemini analysis */}
        {stateFPI && (
          <div className="grid gap-4 md:grid-cols-2">
            {weather && <WeatherStrip weather={weather} />}
            <GeminiWeightsCard fpi={stateFPI} />
          </div>
        )}

        <div className="grid gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
            <StateCountyMap
              stateAbbr={stateAbbr}
              selectedFips={selected}
              onSelect={setSelected}
            />
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">County ranking</CardTitle>
                <div className="mt-2 flex flex-wrap gap-2">
                  <div className="relative flex-1 min-w-[160px]">
                    <Search className="pointer-events-none absolute left-2 top-2 h-3.5 w-3.5 text-muted-foreground" />
                    <Input value={q} onChange={(e) => setQ(e.target.value)}
                      placeholder="Search county…" className="h-8 pl-7 text-xs" />
                  </div>
                  {(["all","critical","action","warning","watch","prepared"] as const).map((t) => (
                    <Button key={t} size="sm" variant={trig === t ? "secondary" : "ghost"}
                      onClick={() => setTrig(t)} className="h-8 text-xs capitalize">{t}</Button>
                  ))}
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="overflow-hidden rounded-md border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                      <tr>
                        <th className="px-3 py-2 text-left">County</th>
                        <th className="px-3 py-2 text-right">Pop.</th>
                        <th className="px-3 py-2 text-right">Score</th>
                        <th className="px-3 py-2 text-right">Level</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ranking.map((r) => (
                        <tr key={r.fips}
                          className={`cursor-pointer border-t transition-colors hover:bg-accent/40 ${selected === r.fips ? "bg-accent/60" : ""}`}
                          onClick={() => setSelected(r.fips)}>
                          <td className="px-3 py-2 font-medium">{r.name}</td>
                          <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">{r.pop.toLocaleString()}</td>
                          <td className={`px-3 py-2 text-right tabular-nums font-semibold ${TRIGGER_COLOR[r.level] ?? ""}`}>{r.total}</td>
                          <td className="px-3 py-2 text-right"><RiskBadge level={r.level} /></td>
                        </tr>
                      ))}
                      {ranking.length === 0 && (
                        <tr><td colSpan={4} className="px-3 py-6 text-center text-sm text-muted-foreground">No counties match.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-base">Top-risk counties</CardTitle></CardHeader>
              <CardContent>
                <ScoreBarChart data={ranking.slice(0, 10).map((r) => ({ name: r.name, score: r.total }))} />
              </CardContent>
            </Card>
          </div>

          <div className="space-y-4">
            {/* Live county FPI panel */}
            {countyFPI && selected && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">
                    {countyFPI.county_name} — Live FPI
                    <span className={`ml-2 text-[10px] font-normal ${countyFPI.gemini_source === "gemini" ? "text-emerald-600" : "text-muted-foreground"}`}>
                      {countyFPI.gemini_source === "gemini" ? "● Gemini" : "● Baseline"}
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-xs space-y-3">
                  <div className="flex items-center gap-2">
                    <span className={`text-2xl font-bold ${TRIGGER_COLOR[countyFPI.trigger] ?? ""}`}>
                      {Math.round(countyFPI.risk_score)}
                    </span>
                    <RiskBadge level={countyFPI.trigger as any} />
                  </div>
                  {countyFPI.reasoning && (
                    <p className="text-muted-foreground italic border-l-2 border-muted pl-2">{countyFPI.reasoning}</p>
                  )}
                  <div className="space-y-1.5">
                    {Object.entries(countyFPI.weights ?? {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                      <div key={k} className="flex items-center gap-2">
                        <span className="w-28 shrink-0 text-muted-foreground capitalize">{k.replace(/_/g, " ")}</span>
                        <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                          <div className="h-full rounded-full bg-primary" style={{ width: `${Math.round(Number(v) * 100)}%` }} />
                        </div>
                        <span className="w-8 text-right font-mono">{Math.round(Number(v) * 100)}%</span>
                      </div>
                    ))}
                  </div>
                  {countyFPI.top_factors?.length > 0 && (
                    <div>
                      <p className="font-medium text-foreground mb-1">Top factors</p>
                      {countyFPI.top_factors.map((f, i) => (
                        <p key={i} className="text-muted-foreground">· {f}</p>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
            {selected && <CountyDetailPanel fips={selected} />}
          </div>
        </div>
      </div>
    </AppShell>
  );
};

export default StateDashboard;