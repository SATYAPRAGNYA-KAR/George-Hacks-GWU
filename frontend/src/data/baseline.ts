// Deterministic baseline data generator for all 50 states + counties.
// Stable across reloads via FIPS-seeded RNG. Each metric tagged source='baseline', freshness='baseline'.

import type {
  CountyFPIDetail,
  MetricValue,
  StateFPIDetail,
} from "@/types/foodready";
import {
  computeCountyComponents,
  computeCountyTotal,
  computeStateFPI,
  coverageFromMetrics,
  triggerForScore,
} from "@/lib/fpi";
import { rngFor, intRange, biasToward } from "@/lib/seed";
import { US_STATES, STATE_CENTROIDS } from "@/data/states";
import { ALL_COUNTIES } from "@/data/counties";

const NOW_ISO = new Date().toISOString();

// State-level risk bias (0=lower risk, 1=higher risk) — gives realistic variance per region
const STATE_BIAS: Record<string, number> = {
  // Higher-risk: rural Appalachia, Gulf, drought-prone
  WV: 0.72, MS: 0.74, KY: 0.66, LA: 0.70, AL: 0.62, AR: 0.62, NM: 0.60, OK: 0.56,
  IA: 0.58, // demo state moderate-high so seeded counties stand out
  TX: 0.55, FL: 0.55, GA: 0.50, SC: 0.52, TN: 0.50, MO: 0.48, IN: 0.45, OH: 0.42,
  MI: 0.46, IL: 0.44, KS: 0.42, NE: 0.40, ND: 0.36, SD: 0.40, MT: 0.42, ID: 0.40,
  AZ: 0.50, NV: 0.46, UT: 0.36, CO: 0.34, WY: 0.40, OR: 0.40, WA: 0.34, AK: 0.55,
  HI: 0.45, CA: 0.42, NY: 0.36, NJ: 0.32, PA: 0.40, MD: 0.34, DE: 0.36, CT: 0.30,
  MA: 0.28, ME: 0.40, NH: 0.30, VT: 0.34, RI: 0.32, VA: 0.36, NC: 0.46, WI: 0.38,
  MN: 0.34,
};

const bias = (a: string) => STATE_BIAS[a] ?? 0.45;

function mkMetric(
  rng: () => number,
  bias01: number,
  source = "baseline",
  freshness: MetricValue["freshness"] = "baseline",
): MetricValue {
  const raw = biasToward(rng(), bias01, 0.55);
  return {
    value: Math.round(raw * 100 * 10) / 10,
    source,
    freshness,
    asOf: NOW_ISO,
  };
}

function generateCountyMetrics(fips: string, stateAbbr: string): CountyFPIDetail["metrics"] {
  const b = bias(stateAbbr);
  const rng = rngFor(`county:${fips}`);
  return {
    alertCount: mkMetric(rng, b * 0.7),
    alertSeverity: mkMetric(rng, b * 0.8),
    fema: mkMetric(rng, b * 0.5),
    drought: mkMetric(rng, b * 0.7),
    poverty: mkMetric(rng, b),
    noVehicle: mkMetric(rng, b * 0.6),
    svi: mkMetric(rng, b),
    foodInsecurity: mkMetric(rng, b * 0.95),
    childFoodInsecurity: mkMetric(rng, b * 0.95),
    foodAccess: mkMetric(rng, b * 0.85),
    retailerScarcity: mkMetric(rng, b * 0.8),
    stockShortfall: mkMetric(rng, b * 0.7),
    voucherShortfall: mkMetric(rng, b * 0.65),
  };
}

/** Generate a synthetic county for any state that has no seeded counties. */
export function syntheticCountiesForState(stateAbbr: string): {
  fips: string;
  stateAbbr: string;
  name: string;
  population: number;
  centroid: [number, number];
}[] {
  const seeded = ALL_COUNTIES.filter((c) => c.stateAbbr === stateAbbr);
  if (seeded.length > 0) return [];

  const stateInfo = US_STATES.find((s) => s.abbr === stateAbbr);
  if (!stateInfo) return [];
  const center = STATE_CENTROIDS[stateAbbr] ?? [39, -98];
  const rng = rngFor(`synth:${stateAbbr}`);
  const count = intRange(rng, 4, 6);
  const out: ReturnType<typeof syntheticCountiesForState> = [];
  for (let i = 0; i < count; i++) {
    const lat = center[0] + (rng() - 0.5) * 3.5;
    const lng = center[1] + (rng() - 0.5) * 4.5;
    const pop = intRange(rng, 18_000, 600_000);
    const idx = String(i + 1).padStart(3, "0");
    out.push({
      fips: `${stateInfo.fips}${idx}`,
      stateAbbr,
      name: `${stateAbbr} District ${i + 1}`,
      population: pop,
      centroid: [lat, lng],
    });
  }
  return out;
}

/** Build a CountyFPIDetail for any FIPS, using seeded data if available. */
export function getCountyFPIDetail(fips: string, stateAbbr: string, communityAdjustment = 0): CountyFPIDetail {
  const metrics = generateCountyMetrics(fips, stateAbbr);

  // If seeded county exists, blend its components into matching metrics so seeded counties keep their flavor.
  const seeded = ALL_COUNTIES.find((c) => c.fips === fips) as any;
  if (seeded?.components) {
    // Override key metrics so total roughly matches seeded composite
    const c = seeded.components;
    metrics.alertSeverity = { ...metrics.alertSeverity, value: clamp01(c.shockExposure * 1.05) };
    metrics.drought = { ...metrics.drought, value: clamp01(c.shockExposure * 0.95) };
    metrics.poverty = { ...metrics.poverty, value: clamp01(c.vulnerability * 1.0) };
    metrics.foodInsecurity = { ...metrics.foodInsecurity, value: clamp01(c.vulnerability * 1.05) };
    metrics.foodAccess = { ...metrics.foodAccess, value: clamp01(c.supplyCapacity * 1.0) };
    metrics.retailerScarcity = { ...metrics.retailerScarcity, value: clamp01(c.supplyCapacity * 1.0) };
    metrics.stockShortfall = { ...metrics.stockShortfall, value: clamp01(c.responseReadiness * 1.05) };
    metrics.voucherShortfall = { ...metrics.voucherShortfall, value: clamp01(c.responseReadiness * 0.95) };
    if (seeded.seedRich) {
      // Iowa seeded: tag a couple of metrics as "fresh" baseline-plus
      metrics.alertCount = { ...metrics.alertCount, source: "NWS (seeded)", freshness: "fresh" };
      metrics.fema = { ...metrics.fema, source: "FEMA (seeded)", freshness: "fresh" };
    }
  }

  const components = computeCountyComponents(metrics);
  const total = computeCountyTotal(components, undefined, communityAdjustment);
  const coverage = coverageFromMetrics(metrics);

  return {
    countyFips: fips,
    total,
    trigger: triggerForScore(total),
    components,
    metrics,
    coverage,
    communityAdjustment,
    asOf: NOW_ISO,
  };
}

const clamp01 = (n: number) => Math.max(0, Math.min(100, n));

/** Build a StateFPIDetail using all known counties (seeded + synthetic). */
export function getStateFPIDetail(
  stateAbbr: string,
  countyFPIs: { fips: string; total: number; trigger: any; population: number }[],
  extras?: { openIncidents?: number; communitySignals24h?: number },
): StateFPIDetail {
  const totalPop = countyFPIs.reduce((a, c) => a + c.population, 0) || 1;
  const b = bias(stateAbbr);
  const rng = rngFor(`statefpi:${stateAbbr}`);

  // Statewide hazard burden = pop-weighted shock proxy (use seeded county avg + bias)
  const hazardBurden = clamp01(50 + (b - 0.4) * 80 + (rng() - 0.5) * 12);
  const logisticsDisruption = clamp01(35 + (b - 0.4) * 70 + (rng() - 0.5) * 14);
  const responseCapacity = clamp01(35 + (b - 0.4) * 60 + (rng() - 0.5) * 12);
  const coverage = stateAbbr === "IA" ? "partial" : "baseline";

  return computeStateFPI({
    stateAbbr,
    countyScores: countyFPIs.map((c) => ({
      fips: c.fips,
      total: c.total,
      population: c.population,
      trigger: c.trigger,
    })),
    totalPopulation: totalPop,
    hazardBurden,
    logisticsDisruption,
    responseCapacity,
    openIncidents: extras?.openIncidents ?? 0,
    communitySignals24h: extras?.communitySignals24h ?? 0,
    coverage,
    asOf: NOW_ISO,
  });
}
