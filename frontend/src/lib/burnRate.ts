import type { Organization } from "@/types/foodready";

/** Average lbs of food distributed per household per day (USDA baseline) */
const LBS_PER_HH_PER_DAY = 4.5;

/** Conservative surge multiplier during an active incident */
const SURGE_MULTIPLIER = 1.4;

export interface BurnRateResult {
  /** Estimated households currently being served (from open requests) */
  activeHouseholds: number;
  /** Estimated lbs consumed per day */
  dailyConsumptionLbs: number;
  /** Projected days of stock remaining. Infinity if no active load. */
  daysOfSupply: number;
  /** Risk band */
  status: "critical" | "warning" | "ok" | "unknown";
  /** Whether the estimate used surge multiplier */
  surgeActive: boolean;
}

/**
 * Compute burn rate for a single organization.
 *
 * @param org          The organization with current foodStockLbs
 * @param openRequests Count of open (non-closed, non-resolved) requests in the org's covered counties
 * @param avgHhSize    Average household size from request data (default 3.5)
 * @param surgeActive  Whether an active incident is ongoing (multiplies consumption)
 */
export function computeBurnRate(
  org: Organization,
  openRequests: number,
  avgHhSize = 3.5,
  surgeActive = false,
): BurnRateResult {
  if (org.foodStockLbs <= 0) {
    return {
      activeHouseholds: 0,
      dailyConsumptionLbs: 0,
      daysOfSupply: 0,
      status: "critical",
      surgeActive,
    };
  }

  const activeHouseholds = Math.round(openRequests * avgHhSize);

  if (activeHouseholds === 0) {
    return {
      activeHouseholds: 0,
      dailyConsumptionLbs: 0,
      daysOfSupply: Infinity,
      status: "ok",
      surgeActive,
    };
  }

  const multiplier = surgeActive ? SURGE_MULTIPLIER : 1.0;
  const dailyConsumptionLbs = activeHouseholds * LBS_PER_HH_PER_DAY * multiplier;
  const daysOfSupply = org.foodStockLbs / dailyConsumptionLbs;

  const status: BurnRateResult["status"] =
    daysOfSupply <= 3
      ? "critical"
      : daysOfSupply <= 7
      ? "warning"
      : "ok";

  return {
    activeHouseholds,
    dailyConsumptionLbs: Math.round(dailyConsumptionLbs),
    daysOfSupply: Math.round(daysOfSupply * 10) / 10,
    status,
    surgeActive,
  };
}

/** Aggregate burn rate across multiple orgs covering a county */
export function aggregateBurnRate(results: BurnRateResult[]): {
  totalDailyLbs: number;
  minDaysOfSupply: number;
  status: BurnRateResult["status"];
} {
  const finite = results.filter((r) => isFinite(r.daysOfSupply));
  const totalDailyLbs = results.reduce((s, r) => s + r.dailyConsumptionLbs, 0);
  const minDaysOfSupply =
    finite.length > 0 ? Math.min(...finite.map((r) => r.daysOfSupply)) : Infinity;
  const status =
    minDaysOfSupply <= 3
      ? "critical"
      : minDaysOfSupply <= 7
      ? "warning"
      : "ok";
  return { totalDailyLbs, minDaysOfSupply, status };
}