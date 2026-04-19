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

// ─── Add these to frontend/src/lib/api.ts ───
// (paste after the existing SignalReportRequest interface and before the helpers section)

// ---------------------------------------------------------------------------
// Community Requests
// ---------------------------------------------------------------------------

export type RequestStatus =
  | "submitted" | "screening" | "verified" | "assigned"
  | "in_transit" | "resolved" | "escalated" | "closed";

export type RequestUrgency = "urgent_24h" | "moderate_week" | "low_general";

export interface StatusHistoryEntry {
  status:      RequestStatus;
  timestamp:   string;
  note:        string;
  assigned_org?: string;
}

export interface CommunityRequest {
  reference:          string;
  state_abbr:         string;
  county_fips:        string;
  city:               string;
  zip:                string;
  type:               string;
  urgency:            RequestUrgency;
  household_size:     number;
  description:        string;
  contact?:           string;
  contact_email?:     string;
  status:             RequestStatus;
  status_history:     StatusHistoryEntry[];
  assigned_org?:      string;
  assigned_org_name?: string;
  resolution_note?:   string;
  created_at:         string;
  updated_at:         string;
}

export interface SubmitRequestPayload {
  state_abbr:     string;
  county_fips:    string;
  city?:          string;
  zip?:           string;
  type:           string;
  urgency:        RequestUrgency;
  household_size: number;
  description:    string;
  contact?:       string;
  contact_email?: string;
}

export interface UpdateStatusPayload {
  status:             RequestStatus;
  note?:              string;
  assigned_org?:      string;
  assigned_org_name?: string;
  resolution_note?:   string;
}

export interface RequestStats {
  state_abbr: string;
  total:      number;
  open:       number;
  by_status:  Record<RequestStatus, number>;
}

// Submit a new community request — saved to MongoDB
export const submitCommunityRequest = (payload: SubmitRequestPayload) =>
  post<{ status: string; reference: string; request: CommunityRequest }>(
    "/api/requests", payload
  );

// Look up a request by reference number (FR-XXXX-XXXX)
export const fetchRequestByRef = (reference: string) =>
  get<CommunityRequest>(`/api/requests/${reference.trim().toUpperCase()}`);

// List requests — used by responder portal
export const fetchRequests = (params: {
  state_abbr?: string;
  county_fips?: string;
  status?: RequestStatus;
  urgency?: RequestUrgency;
  limit?: number;
  skip?: number;
}) => {
  const q = new URLSearchParams();
  if (params.state_abbr)  q.set("state_abbr",  params.state_abbr);
  if (params.county_fips) q.set("county_fips", params.county_fips);
  if (params.status)      q.set("status",      params.status);
  if (params.urgency)     q.set("urgency",      params.urgency);
  if (params.limit)       q.set("limit",        String(params.limit));
  if (params.skip)        q.set("skip",         String(params.skip));
  return get<{ count: number; total: number; requests: CommunityRequest[] }>(
    `/api/requests?${q.toString()}`
  );
};

// Update status — used by responder portal
export const updateRequestStatus = (reference: string, payload: UpdateStatusPayload) =>
  (async () => {
    const res = await fetch(`${(import.meta.env.VITE_API_BASE as string) ?? ""}/api/requests/${reference.toUpperCase()}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`PATCH /api/requests/${reference}/status → ${res.status}`);
    return res.json() as Promise<{ status: string; request: CommunityRequest }>;
  })();

// Stats for dashboard widgets
export const fetchRequestStats = (stateAbbr: string) =>
  get<RequestStats>(`/api/requests/stats/${stateAbbr}`);

// ---------------------------------------------------------------------------
// Status metadata helpers (used in Community and Responder pages)
// ---------------------------------------------------------------------------

export const STATUS_META: Record<RequestStatus, { label: string; color: string; bg: string }> = {
  submitted:  { label: "Submitted",           color: "text-blue-700",   bg: "bg-blue-50" },
  screening:  { label: "Under review",        color: "text-yellow-700", bg: "bg-yellow-50" },
  verified:   { label: "Verified",            color: "text-indigo-700", bg: "bg-indigo-50" },
  assigned:   { label: "Assigned",            color: "text-purple-700", bg: "bg-purple-50" },
  in_transit: { label: "Help on the way",     color: "text-orange-700", bg: "bg-orange-50" },
  resolved:   { label: "Resolved",            color: "text-emerald-700",bg: "bg-emerald-50" },
  escalated:  { label: "Escalated",           color: "text-red-700",    bg: "bg-red-50" },
  closed:     { label: "Closed",              color: "text-gray-600",   bg: "bg-gray-100" },
};

export const STATUS_TRANSITIONS: Record<RequestStatus, RequestStatus[]> = {
  submitted:  ["screening", "verified", "escalated", "closed"],
  screening:  ["verified", "escalated", "closed"],
  verified:   ["assigned", "escalated", "closed"],
  assigned:   ["in_transit", "escalated", "closed"],
  in_transit: ["resolved", "escalated", "closed"],
  resolved:   [],
  escalated:  ["assigned", "closed"],
  closed:     [],
};