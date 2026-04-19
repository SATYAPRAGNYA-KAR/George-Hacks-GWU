import rawCorridors from "./supply_corridors.json";

export type CorridorStatus = "operational" | "at_risk" | "degraded" | "blocked";

export interface DestinationCommunity {
  community_id: string;
  name: string;
  population: number;
  food_insecurity_rate: number;
  dependency_weight: number;       // 0-1: how much this community depends on this corridor
}

export interface SupplyCorridor {
  id: string;
  name: string;
  source_region: string;
  crop_types: string[];
  destination_communities: DestinationCommunity[];
  primary_route: string;
  backup_route?: string;
  source_counties: string[];
  waypoints: { state: string; county: string }[];
}

export const ALL_CORRIDORS: SupplyCorridor[] = (rawCorridors as any).corridors;

/**
 * Compute a corridor's disruption status from a shock score (0-100).
 * The shock score comes from the weather snapshot or FPI component.
 */
export function corridorStatusFromShock(shockScore: number): CorridorStatus {
  if (shockScore >= 75) return "blocked";
  if (shockScore >= 55) return "degraded";
  if (shockScore >= 35) return "at_risk";
  return "operational";
}

export const STATUS_META: Record<CorridorStatus, { label: string; color: string; bg: string; border: string }> = {
  operational: { label: "Operational", color: "text-emerald-700", bg: "bg-emerald-50", border: "border-emerald-200" },
  at_risk:     { label: "At Risk",     color: "text-yellow-700",  bg: "bg-yellow-50",  border: "border-yellow-200" },
  degraded:    { label: "Degraded",    color: "text-orange-700",  bg: "bg-orange-50",  border: "border-orange-200" },
  blocked:     { label: "Blocked",     color: "text-red-700",     bg: "bg-red-50",      border: "border-red-200"    },
};