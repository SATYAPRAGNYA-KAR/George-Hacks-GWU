import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { USMap } from "@/components/maps/USMap";
import { MetricCard, MetricStrip } from "@/components/MetricCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { RiskBadge } from "@/components/RiskBadge";
import { US_STATES } from "@/data/states";
import { useAppStore, generateNationalTrend } from "@/store/appStore";
import { Activity, AlertTriangle, BarChart3, Globe, Search, Users, Wifi, WifiOff, RefreshCw } from "lucide-react";
import { TrendChart, ScoreBarChart } from "@/components/charts/Charts";
import { fetchAllStatesFPI, type StateFPISummary, scoreToTrigger } from "@/lib/api";
import { TRIGGER_META, triggerForScore } from "@/lib/risk";
import { stateAverageScore, getCountiesForState } from "@/store/appStore";

const TRIGGER_COLORS: Record<string, string> = {
  prepared: "text-emerald-600",
  watch: "text-yellow-600",
  warning: "text-orange-500",
  action: "text-red-500",
  critical: "text-red-700",
};

const LiveBadge = ({ source }: { source?: string }) =>
  source === "gemini" ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
      Live · Gemini
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
      <span className="h-1.5 w-1.5 rounded-full bg-yellow-500" />
      Baseline
    </span>
  );

const NationalDashboard = () => {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<"all" | "alerts">("all");
  const requests = useAppStore((s) => s.requests);
  const triggers = useAppStore((s) => s.triggers);

  // Live backend data — all 50 states
  const {
    data: liveData,
    isLoading: liveLoading,
    isError: liveError,
    refetch,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ["fpi-states"],
    queryFn: () => fetchAllStatesFPI(),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  // Build a map of stateAbbr → live FPI for O(1) lookup
  const liveFPIMap = useMemo(() => {
    const map: Record<string, StateFPISummary> = {};
    (liveData?.states ?? []).forEach((s) => { map[s.state_abbr] = s; });
    return map;
  }, [liveData]);

  const stateRows = useMemo(() => {
    return US_STATES.map((s) => {
      const live = liveFPIMap[s.abbr];
      const baselineAvg = stateAverageScore(s.abbr);
      const score  = live?.risk_score ?? baselineAvg ?? 30;
      const trigger = live
        ? live.trigger
        : triggerForScore(score ?? 30);
      const counties = getCountiesForState(s.abbr).length;
      const alerts = triggers.filter(
        (t) => t.stateAbbr === s.abbr &&
          ["warning", "action", "critical"].includes(t.thresholdCrossed)
      ).length + (live && ["warning","action","critical"].includes(live.trigger) ? 1 : 0);
      const reqs = requests.filter((r) => r.stateAbbr === s.abbr).length;
      return {
        ...s, score, trigger, counties, alerts, reqs,
        isLive: !!live,
        dominantDriver: live?.dominant_driver ?? null,
        weatherStatus:  live?.weather_status ?? null,
      };
    })
      .filter((r) => r.name.toLowerCase().includes(q.toLowerCase()) || r.abbr.toLowerCase().includes(q.toLowerCase()))
      .filter((r) => filter === "alerts" ? r.alerts > 0 : true)
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  }, [q, filter, requests, triggers, liveFPIMap]);

  const liveStates   = stateRows.filter((r) => r.isLive);
  const natlAvg = liveStates.length
    ? Math.round(liveStates.reduce((a, b) => a + (b.score ?? 0), 0) / liveStates.length * 10) / 10
    : 0;
  const totalAlerts = stateRows.reduce((a, b) => a + b.alerts, 0);
  const trend = generateNationalTrend(30);

  return (
    <AppShell>
      <div className="space-y-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold">National dashboard</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              U.S.-wide food access risk · click any state to drill into counties.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {liveLoading && (
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <RefreshCw className="h-3 w-3 animate-spin" /> Fetching live data…
              </span>
            )}
            {!liveLoading && !liveError && liveData && (
              <span className="flex items-center gap-1.5 text-xs text-emerald-600">
                <Wifi className="h-3 w-3" />
                Live · NOAA · FEMA · Gemini
                {dataUpdatedAt && (
                  <span className="text-muted-foreground">
                    · updated {new Date(dataUpdatedAt).toLocaleTimeString()}
                  </span>
                )}
              </span>
            )}
            {!liveLoading && liveError && (
              <span className="flex items-center gap-1.5 text-xs text-yellow-600">
                <WifiOff className="h-3 w-3" /> Baseline data (backend offline)
              </span>
            )}
            <Button size="sm" variant="outline" onClick={() => refetch()} className="h-7 text-xs gap-1">
              <RefreshCw className="h-3 w-3" /> Refresh
            </Button>
          </div>
        </div>

        <MetricStrip>
          <MetricCard label="States monitored" value={US_STATES.length}
            hint={liveData ? `${liveData.states.length} with live data` : "Iowa fully seeded"}
            icon={<Globe className="h-4 w-4" />} />
          <MetricCard label="Counties monitored"
            value={US_STATES.reduce((a, s) => a + getCountiesForState(s.abbr).length, 0)}
            icon={<BarChart3 className="h-4 w-4" />} />
          <MetricCard label="Active alerts" value={totalAlerts}
            hint="Warning+ triggers" icon={<AlertTriangle className="h-4 w-4" />} accent="text-risk-action" />
          <MetricCard label="Open requests"
            value={requests.filter((r) => r.status !== "resolved").length}
            hint={`${requests.length} total`} icon={<Users className="h-4 w-4" />} />
          <MetricCard label="National avg risk" value={natlAvg}
            hint={liveData ? "Live backend score" : "Seeded baseline"}
            icon={<Activity className="h-4 w-4" />} />
        </MetricStrip>

        <div className="grid gap-5 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <USMap liveFPIMap={liveFPIMap} />
          </div>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">State ranking</CardTitle>
              <div className="mt-2 flex gap-2">
                <div className="relative flex-1">
                  <Search className="pointer-events-none absolute left-2 top-2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input value={q} onChange={(e) => setQ(e.target.value)}
                    placeholder="Search state…" className="h-8 pl-7 text-xs" />
                </div>
                <Button size="sm" variant={filter === "all" ? "secondary" : "ghost"}
                  onClick={() => setFilter("all")} className="h-8 text-xs">All</Button>
                <Button size="sm" variant={filter === "alerts" ? "secondary" : "ghost"}
                  onClick={() => setFilter("alerts")} className="h-8 text-xs">Alerts</Button>
              </div>
            </CardHeader>
            <CardContent className="max-h-[420px] overflow-y-auto pt-0">
              <ul className="divide-y">
                {stateRows.map((r) => (
                  <li
                    key={r.abbr}
                    className="flex cursor-pointer items-center gap-2 py-2 text-sm hover:bg-accent/40 px-1 rounded-md transition-colors"
                    onClick={() => nav(`/state/${r.abbr}`)}
                  >
                    <span className="w-7 shrink-0 font-mono text-xs text-muted-foreground">{r.abbr}</span>
                    <span className="flex-1 truncate text-xs font-medium">{r.name}</span>
                    {r.isLive && <LiveBadge source="gemini" />}
                    <RiskBadge level={r.trigger as any} />
                    <span className={`w-8 text-right text-xs font-semibold tabular-nums ${TRIGGER_COLORS[r.trigger] ?? ""}`}>
                      {Math.round(r.score ?? 0)}
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader><CardTitle className="text-base">National risk trend (30 days)</CardTitle></CardHeader>
            <CardContent><TrendChart data={trend} /></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Highest-risk states</CardTitle></CardHeader>
            <CardContent>
              <ScoreBarChart data={stateRows.slice(0, 10).map((r) => ({ name: r.abbr, score: Math.round(r.score ?? 0) }))} />
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
};

export default NationalDashboard;