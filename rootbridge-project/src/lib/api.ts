export const API_BASE = "https://food-insecurity-api.onrender.com";

export type AlertLevel = "Watch" | "Warning" | "Action" | string;

export interface Alert {
  alert_id: string;
  community_id: string;
  community_name: string;
  level: AlertLevel;
  risk_score: number;
  generated_at: string;
  headline: string;
  explanation: string;
  top_factors: string[];
  recommended_actions: string[];
  sms_body: string;
  voice_script: string;
  corridor_id: string;
  data_quality: string;
  component_breakdown: Record<string, number>;
}

export interface RiskCommunity {
  community_id: string;
  community_name: string;
  corridor_id: string;
  risk_score: number;
  data_quality: string;
  components: Record<string, number>;
  top_factors: string[];
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  alerts: () =>
    fetchJson<{ count: number; generated_at: string; alerts: Alert[] }>("/api/alerts"),
  risk: () =>
    fetchJson<{ count: number; generated_at: string; communities: RiskCommunity[] }>(
      "/api/risk",
    ),
  communityAlert: (id: string) => fetchJson<Alert>(`/api/alerts/${id}`),
  communityRisk: (id: string) => fetchJson<RiskCommunity>(`/api/risk/${id}`),
  refreshAlerts: () =>
    fetchJson<unknown>("/api/alerts/refresh", { method: "POST" }),
  regions: () => fetchJson<unknown>("/api/regions"),
};

export function levelClasses(level: string) {
  const l = level.toLowerCase();
  if (l === "action")
    return "bg-[var(--level-action)] text-destructive-foreground";
  if (l === "warning")
    return "bg-[var(--level-warning)] text-destructive-foreground";
  if (l === "watch") return "bg-[var(--level-watch)] text-foreground";
  return "bg-[var(--level-ok)] text-primary-foreground";
}

export function riskColor(score: number) {
  if (score >= 80) return "var(--level-action)";
  if (score >= 60) return "var(--level-warning)";
  if (score >= 40) return "var(--level-watch)";
  return "var(--level-ok)";
}
