// FPI engines — county and state FPI calculated separately per spec.
// All inputs normalized to 0-100 risk (higher = worse).

import type {
  ComponentScores,
  CountyFPIDetail,
  CoverageLevel,
  MetricValue,
  StateFPIDetail,
  TriggerLevel,
} from "@/types/foodready";

export const COUNTY_DOMAIN_WEIGHTS = {
  shockExposure: 0.30,
  vulnerability: 0.30,
  supplyCapacity: 0.25,
  responseReadiness: 0.15,
};

export const SHOCK_SUBWEIGHTS = {
  alertCount: 0.30,
  alertSeverity: 0.25,
  fema: 0.20,
  drought: 0.25,
};

export const VULN_SUBWEIGHTS = {
  poverty: 0.25,
  noVehicle: 0.15,
  svi: 0.25,
  foodInsecurity: 0.20,
  childFoodInsecurity: 0.15,
};

export const SUPPLY_SUBWEIGHTS = {
  foodAccess: 0.60,
  retailerScarcity: 0.40,
};

export const READINESS_SUBWEIGHTS = {
  stockShortfall: 0.60,
  voucherShortfall: 0.40,
};

export const STATE_FPI_WEIGHTS = {
  hotspotPressure: 0.22,
  pctCountiesWarningPlus: 0.18,
  hazardBurden: 0.16,
  logisticsDisruption: 0.12,
  responseCapacity: 0.12,
  openIncidentPressure: 0.10,
  communitySignalSurge: 0.10,
};

export const TRIGGER_THRESHOLDS = {
  watch: 40,
  warning: 60,
  action: 75,
  critical: 90,
};

export function triggerForScore(score: number): TriggerLevel {
  if (score >= TRIGGER_THRESHOLDS.critical) return "critical";
  if (score >= TRIGGER_THRESHOLDS.action) return "action";
  if (score >= TRIGGER_THRESHOLDS.warning) return "warning";
  if (score >= TRIGGER_THRESHOLDS.watch) return "watch";
  return "prepared";
}

const r1 = (n: number) => Math.round(n * 10) / 10;
const clamp = (n: number, min = 0, max = 100) => Math.max(min, Math.min(max, n));

// ---------- County FPI ----------
export function computeCountyComponents(metrics: CountyFPIDetail["metrics"]): ComponentScores {
  const shockExposure =
    metrics.alertCount.value * SHOCK_SUBWEIGHTS.alertCount +
    metrics.alertSeverity.value * SHOCK_SUBWEIGHTS.alertSeverity +
    metrics.fema.value * SHOCK_SUBWEIGHTS.fema +
    metrics.drought.value * SHOCK_SUBWEIGHTS.drought;

  const vulnerability =
    metrics.poverty.value * VULN_SUBWEIGHTS.poverty +
    metrics.noVehicle.value * VULN_SUBWEIGHTS.noVehicle +
    metrics.svi.value * VULN_SUBWEIGHTS.svi +
    metrics.foodInsecurity.value * VULN_SUBWEIGHTS.foodInsecurity +
    metrics.childFoodInsecurity.value * VULN_SUBWEIGHTS.childFoodInsecurity;

  const supplyCapacity =
    metrics.foodAccess.value * SUPPLY_SUBWEIGHTS.foodAccess +
    metrics.retailerScarcity.value * SUPPLY_SUBWEIGHTS.retailerScarcity;

  const responseReadiness =
    metrics.stockShortfall.value * READINESS_SUBWEIGHTS.stockShortfall +
    metrics.voucherShortfall.value * READINESS_SUBWEIGHTS.voucherShortfall;

  return {
    shockExposure: r1(shockExposure),
    vulnerability: r1(vulnerability),
    supplyCapacity: r1(supplyCapacity),
    responseReadiness: r1(responseReadiness),
  };
}

export function computeCountyTotal(
  components: ComponentScores,
  weights = COUNTY_DOMAIN_WEIGHTS,
  communityAdjustment = 0,
): number {
  const base =
    components.shockExposure * weights.shockExposure +
    components.vulnerability * weights.vulnerability +
    components.supplyCapacity * weights.supplyCapacity +
    components.responseReadiness * weights.responseReadiness;
  return r1(clamp(base + communityAdjustment));
}

/** Worst freshness across all metrics determines coverage. */
export function coverageFromMetrics(metrics: CountyFPIDetail["metrics"]): CoverageLevel {
  const all = Object.values(metrics) as MetricValue[];
  const hasLive = all.some((m) => m.freshness === "live");
  const hasFresh = all.some((m) => m.freshness === "fresh");
  const allBaseline = all.every((m) => m.freshness === "baseline");
  const anyVeryStale = all.some((m) => m.freshness === "very_stale");
  if (allBaseline) return "baseline";
  if (anyVeryStale) return "delayed";
  if (hasLive && hasFresh) return "live";
  if (hasLive || hasFresh) return "partial";
  return "baseline";
}

// ---------- State FPI ----------
export interface StateFPIInputs {
  stateAbbr: string;
  countyScores: { fips: string; total: number; population: number; trigger: TriggerLevel }[];
  hazardBurden: number;          // 0-100, statewide hazard load (avg severity weighted by pop)
  logisticsDisruption: number;   // 0-100, fleet/route disruption proxy
  responseCapacity: number;      // 0-100 risk (higher = worse)
  openIncidents: number;         // count
  communitySignals24h: number;   // count
  totalPopulation: number;
  coverage: CoverageLevel;
  asOf: string;
}

export function computeStateFPI(input: StateFPIInputs): StateFPIDetail {
  const { countyScores, totalPopulation } = input;
  const totalPop = totalPopulation || countyScores.reduce((a, c) => a + c.population, 0) || 1;

  // Population-weighted hotspot pressure: sum(pop * max(0, score-40)) / sum(pop) scaled.
  const hotspotRaw = countyScores.reduce(
    (acc, c) => acc + c.population * Math.max(0, c.total - 40),
    0,
  ) / totalPop;
  const hotspotPressure = r1(clamp(hotspotRaw * 1.6));

  const warningPlus = countyScores.filter(
    (c) => c.trigger === "warning" || c.trigger === "action" || c.trigger === "critical",
  ).length;
  const pctCountiesWarningPlus = r1(
    clamp((warningPlus / Math.max(1, countyScores.length)) * 100),
  );

  const hazardBurden = r1(clamp(input.hazardBurden));
  const logisticsDisruption = r1(clamp(input.logisticsDisruption));
  const responseCapacity = r1(clamp(input.responseCapacity));

  // Open incident pressure: log-scaled count → 0-100
  const openIncidentPressure = r1(
    clamp(Math.log2(input.openIncidents + 1) * 22),
  );

  // Community signal surge: log-scaled per million pop
  const signalsPerMM = (input.communitySignals24h * 1_000_000) / totalPop;
  const communitySignalSurge = r1(clamp(Math.log2(signalsPerMM + 1) * 18));

  const components = {
    hotspotPressure,
    pctCountiesWarningPlus,
    hazardBurden,
    logisticsDisruption,
    responseCapacity,
    openIncidentPressure,
    communitySignalSurge,
  };

  const total = r1(
    clamp(
      components.hotspotPressure * STATE_FPI_WEIGHTS.hotspotPressure +
        components.pctCountiesWarningPlus * STATE_FPI_WEIGHTS.pctCountiesWarningPlus +
        components.hazardBurden * STATE_FPI_WEIGHTS.hazardBurden +
        components.logisticsDisruption * STATE_FPI_WEIGHTS.logisticsDisruption +
        components.responseCapacity * STATE_FPI_WEIGHTS.responseCapacity +
        components.openIncidentPressure * STATE_FPI_WEIGHTS.openIncidentPressure +
        components.communitySignalSurge * STATE_FPI_WEIGHTS.communitySignalSurge,
    ),
  );

  return {
    stateAbbr: input.stateAbbr,
    total,
    trigger: triggerForScore(total),
    components,
    coverage: input.coverage,
    asOf: input.asOf,
  };
}

// ---------- Trigger metadata ----------
export const TRIGGER_META: Record<
  TriggerLevel,
  { label: string; cssVar: string; description: string; actions: string[] }
> = {
  prepared: {
    label: "Prepared",
    cssVar: "--risk-prepared",
    description: "Routine monitoring",
    actions: ["Routine monitoring", "No responder action required"],
  },
  watch: {
    label: "Watch",
    cssVar: "--risk-watch",
    description: "Alert food security lead",
    actions: ["Alert food security lead", "Monitor daily"],
  },
  warning: {
    label: "Warning",
    cssVar: "--risk-warning",
    description: "Pre-position food stocks",
    actions: ["Pre-position shelf-stable food", "Activate responder review"],
  },
  action: {
    label: "Action",
    cssVar: "--risk-action",
    description: "Activate vouchers, deploy responders",
    actions: ["Activate voucher/cash workflow", "Open food reserves", "Deploy responders"],
  },
  critical: {
    label: "Critical",
    cssVar: "--risk-critical",
    description: "Escalate to state coordination",
    actions: ["Escalate to state", "All channels active", "Emergency reserves"],
  },
};

export function colorForScore(score: number): string {
  return `hsl(var(${TRIGGER_META[triggerForScore(score)].cssVar}))`;
}
