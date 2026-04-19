/**
 * api.ts — typed client for all RootBridge backend endpoints
 *
 * Vite proxies /api → http://localhost:8000 in dev (see vite.config.ts).
 * In production set VITE_API_BASE to the deployed backend URL.
 */

const BASE = (import.meta.env.VITE_API_BASE as string) ?? "";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${path} → ${res.status}: ${body}`);
  }
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body != null ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const b = await res.text().catch(() => "");
    throw new Error(`API ${path} → ${res.status}: ${b}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TriggerLevel = "prepared" | "watch" | "warning" | "action" | "critical";

export interface GeminiWeights {
  shock_exposure: number;
  vulnerability: number;
  supply_capacity: number;
  response_readiness: number;
}

export interface StateFPISummary {
  state_abbr: string;
  state_name: string;
  risk_score: number;
  trigger: TriggerLevel;
  dominant_driver: string;
  top_factors: string[];
  weather_status: "clear" | "impaired" | "blocked";
  shock_score: number;
  gemini_source: "gemini" | "deterministic";
  cached_at: string;
  error?: string;
}

export interface StateFPIDetail extends StateFPISummary {
  state_weights: Record<string, number>;
  reasoning: string;
  recommended_actions: string[];
  weather: WeatherSnapshot;
  vulnerability: VulnerabilityData;
  fema_declarations: number;
}

export interface CountyFPIDetail {
  state_abbr: string;
  county_fips: string;
  county_name: string;
  risk_score: number;
  trigger: TriggerLevel;
  weights: GeminiWeights;
  top_factors: string[];
  reasoning: string;
  weight_rationale: string;
  weather: CountyWeatherSnapshot;
  vulnerability: VulnerabilityData;
  gemini_source: "gemini" | "deterministic";
  cached_at: string;
}

export interface NWSAlert {
  id: string;
  category: string;
  event: string;
  severity: string;
  severity_rank: number;
  affected_area: string;
  areas: string[];
  expires_at: string | null;
  effective_at: string | null;
  headline: string | null;
}

export interface DroughtStatus {
  state_abbr: string;
  none_pct: number;
  d0_pct: number;
  d1_pct: number;
  d2_pct: number;
  d3_pct: number;
  d4_pct: number;
  max_class: string;
  as_of: string;
  source: string;
}

export interface WeatherSnapshot {
  state_abbr: string;
  overall_status: "clear" | "impaired" | "blocked";
  shock_score: number;
  nws_alerts: NWSAlert[];
  active_storms: unknown[];
  firms_anomalies: unknown[];
  drought: DroughtStatus;
  generated_at: string;
}

export interface CountyWeatherSnapshot {
  state_abbr: string;
  county_fips: string;
  overall_status: "clear" | "impaired" | "blocked";
  shock_score: number;
  nws_alerts: NWSAlert[];
  drought: DroughtStatus;
  generated_at: string;
}

export interface VulnerabilityData {
  poverty_pct: number;
  food_insecurity_pct: number;
  no_vehicle_pct: number;
  svi_score: number;
}

export interface RegisterUserRequest {
  email: string;
  name: string;
  role: "public" | "community" | "responder" | "coordinator" | "government" | "admin";
  state_abbr: string;
  county_fips?: string;
  org_name?: string;
  phone?: string;
}

export interface RegisteredUser {
  id: string;
  email: string;
  name: string;
  role: string;
  state_abbr: string;
  county_fips?: string;
  org_name?: string;
  phone?: string;
  created_at: string;
  active: boolean;
  alerts_opt_in: boolean;
}

export interface SignalReportRequest {
  state_abbr: string;
  county_fips: string;
  category: string;
  severity: "low" | "moderate" | "high" | "severe";
  description: string;
  zip_code?: string;
  reporter_fingerprint?: string;
}

// ---------------------------------------------------------------------------
// FPI endpoints
// ---------------------------------------------------------------------------

export const fetchAllStatesFPI = (refresh = false) =>
  get<{ count: number; generated_at: string; states: StateFPISummary[] }>(
    `/api/fpi/states${refresh ? "?refresh=true" : ""}`
  );

export const fetchStateFPI = (stateAbbr: string, refresh = false) =>
  get<StateFPIDetail>(
    `/api/fpi/state/${stateAbbr}${refresh ? "?refresh=true" : ""}`
  );

export const fetchCountyFPI = (
  stateAbbr: string,
  countyFips: string,
  countyName = "",
  refresh = false,
) =>
  get<CountyFPIDetail>(
    `/api/fpi/county/${stateAbbr}/${countyFips}` +
    `?county_name=${encodeURIComponent(countyName)}` +
    `${refresh ? "&refresh=true" : ""}`
  );

// ---------------------------------------------------------------------------
// Weather
// ---------------------------------------------------------------------------

export const fetchWeather = (stateAbbr: string) =>
  get<WeatherSnapshot>(`/api/weather/${stateAbbr}`);

// ---------------------------------------------------------------------------
// User onboarding
// ---------------------------------------------------------------------------

export const registerUser = (req: RegisterUserRequest) =>
  post<{ status: string; user: RegisteredUser }>("/api/users/register", req);

export const fetchUser = (email: string) =>
  get<RegisteredUser>(`/api/users/${encodeURIComponent(email)}`);

// ---------------------------------------------------------------------------
// Community signals
// ---------------------------------------------------------------------------

export const submitSignal = (req: SignalReportRequest) =>
  post<{ status: string; signal: unknown }>("/api/signals", req);

export const fetchSignals = (stateAbbr: string, countyFips?: string) =>
  get<{ count: number; reports: unknown[] }>(
    `/api/signals/${stateAbbr}${countyFips ? `?county_fips=${countyFips}` : ""}`
  );

// ---------------------------------------------------------------------------
// Legacy alerts (Builder 3)
// ---------------------------------------------------------------------------

export interface BackendAlert {
  community_id: string;
  community_name: string;
  level: "Watch" | "Warning" | "Action" | null;
  risk_score: number;
  headline: string;
  recommended_actions: string[];
  sms_body: string;
  voice_script: string;
  generated_at: string;
  data_quality: string;
}

export const fetchAllAlerts = (minLevel: "Watch" | "Warning" | "Action" = "Watch") =>
  get<{ alerts: BackendAlert[] }>(`/api/alerts?min_level=${minLevel}`).then((r) => r.alerts);

export const fetchDisruptions = (regionId: string) =>
  get<{
    region_id: string;
    overall_status: string;
    weather_alerts: NWSAlert[];
    disasters: unknown[];
    route_statuses: unknown[];
    generated_at: string;
  }>(`/api/disruptions/${regionId}`);

// ---------------------------------------------------------------------------
// Crop health (Builder 1)
// ---------------------------------------------------------------------------

export const triggerAnalysis = (
  regionIdOrState: string,
  fastMode = true,
) => {
  const isStateCode = /^[A-Z]{2}$/.test(regionIdOrState.toUpperCase());
  return post<unknown>("/api/analyze", {
    region_id: regionIdOrState.toLowerCase(),
    ...(isStateCode ? { state_abbr: regionIdOrState.toUpperCase() } : {}),
    fast_mode: fastMode,
  });
};

export const fetchCropHealth = (regionId: string) =>
  get<{
    region_id: string;
    summary: {
      alert: string;
      ndvi_current: number | null;
      ndvi_deviation_pct: number | null;
      drought_status: string;
    };
  }>(`/api/crop-health/${regionId}`);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Convert a backend trigger string to the frontend TriggerLevel type */
export function toTriggerLevel(trigger: string | null | undefined): TriggerLevel {
  const map: Record<string, TriggerLevel> = {
    prepared: "prepared", watch: "watch", warning: "warning",
    action: "action", critical: "critical",
    Watch: "watch", Warning: "warning", Action: "action",
  };
  return map[trigger ?? ""] ?? "prepared";
}

/** Map risk_score number → TriggerLevel */
export function scoreToTrigger(score: number): TriggerLevel {
  if (score >= 90) return "critical";
  if (score >= 75) return "action";
  if (score >= 60) return "warning";
  if (score >= 40) return "watch";
  return "prepared";
}