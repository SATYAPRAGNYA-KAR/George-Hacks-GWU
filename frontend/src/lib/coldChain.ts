import type { Organization, DeliveryMode, SupplySourceType } from "@/types/foodready";

/** Delivery modes that require a cold chain to avoid spoilage */
export const COLD_CHAIN_REQUIRED_MODES: DeliveryMode[] = [
  "home_delivery",
  "pantry_pickup",
  "shelter_delivery",
];

/** Supply source types that typically carry perishables */
export const PERISHABLE_SOURCES: SupplySourceType[] = [
  "food_bank_stock",
  "retailer_support",
];

export interface ColdChainCheckResult {
  safe: boolean;
  /** Human-readable warning, null if safe */
  warning: string | null;
  /** Suggested alternative org ids, if mismatch found */
  suggestedAlternativeIds: string[];
}

/**
 * Check whether a proposed logistics route is cold-chain safe.
 *
 * @param org          The org that will handle transport
 * @param deliveryMode The planned delivery mode
 * @param supplySource The supply source type
 * @param allOrgs      Full org list (to find cold-chain alternatives)
 * @param countyFips   Target county (to filter alternatives by coverage)
 */
export function checkColdChain(
  org: Organization,
  deliveryMode: DeliveryMode,
  supplySource: SupplySourceType,
  allOrgs: Organization[],
  countyFips?: string,
): ColdChainCheckResult {
  const modeNeedsCold = COLD_CHAIN_REQUIRED_MODES.includes(deliveryMode);
  const sourceIsPerishable = PERISHABLE_SOURCES.includes(supplySource);

  if (!modeNeedsCold || !sourceIsPerishable || org.coldChain) {
    return { safe: true, warning: null, suggestedAlternativeIds: [] };
  }

  // Mismatch: perishable food, mode requires cold chain, but org has none
  const alternatives = allOrgs.filter(
    (o) =>
      o.id !== org.id &&
      o.coldChain &&
      o.verified &&
      (countyFips ? o.countiesCovered.includes(countyFips) : true),
  );

  return {
    safe: false,
    warning: `${org.name} does not have cold-chain capability. Perishable food routed via "${deliveryMode.replace(/_/g, " ")}" risks spoilage.`,
    suggestedAlternativeIds: alternatives.map((o) => o.id),
  };
}

/** Quick summary label for an org's cold-chain status */
export function coldChainLabel(org: Organization): string {
  return org.coldChain ? "Cold chain ✓" : "No cold chain";
}