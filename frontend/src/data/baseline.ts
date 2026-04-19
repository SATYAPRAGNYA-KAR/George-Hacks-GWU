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

// State-level risk bias (0=lower risk, 1=higher risk)
const STATE_BIAS: Record<string, number> = {
  WV: 0.72, MS: 0.74, KY: 0.66, LA: 0.70, AL: 0.62, AR: 0.62, NM: 0.60, OK: 0.56,
  IA: 0.58,
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
    alertCount:          mkMetric(rng, b * 0.7),
    alertSeverity:       mkMetric(rng, b * 0.8),
    fema:                mkMetric(rng, b * 0.5),
    drought:             mkMetric(rng, b * 0.7),
    poverty:             mkMetric(rng, b),
    noVehicle:           mkMetric(rng, b * 0.6),
    svi:                 mkMetric(rng, b),
    foodInsecurity:      mkMetric(rng, b * 0.95),
    childFoodInsecurity: mkMetric(rng, b * 0.95),
    foodAccess:          mkMetric(rng, b * 0.85),
    retailerScarcity:    mkMetric(rng, b * 0.8),
    stockShortfall:      mkMetric(rng, b * 0.7),
    voucherShortfall:    mkMetric(rng, b * 0.65),
  };
}

// ---------------------------------------------------------------------------
// Real county names per state — used by syntheticCountiesForState
// so "UT District 1" becomes "Salt Lake" etc.
// ---------------------------------------------------------------------------
const REAL_COUNTY_NAMES: Record<string, string[]> = {
  UT: ["Salt Lake","Utah","Davis","Weber","Washington","Cache","Box Elder","Tooele","Iron","Carbon"],
  AL: ["Jefferson","Mobile","Madison","Montgomery","Shelby","Tuscaloosa","Baldwin","Lee","Morgan","Etowah"],
  AK: ["Anchorage","Fairbanks North Star","Matanuska-Susitna","Kenai Peninsula","Juneau","Kodiak Island"],
  AZ: ["Maricopa","Pima","Pinal","Yavapai","Mohave","Yuma","Coconino","Cochise","Apache","Navajo"],
  AR: ["Pulaski","Benton","Washington","Sebastian","Faulkner","Saline","Garland","Craighead","White","Lonoke"],
  CA: ["Alameda","Contra Costa","Marin","Napa","San Francisco","San Mateo","Santa Clara","Solano","Sonoma","Sacramento"],
  CO: ["Denver","El Paso","Arapahoe","Jefferson","Adams","Larimer","Douglas","Weld","Boulder","Pueblo"],
  CT: ["Fairfield","Hartford","Litchfield","Middlesex","New Haven","New London","Tolland","Windham"],
  DE: ["New Castle","Kent","Sussex"],
  FL: ["Broward","Palm Beach","Pinellas","Orange","Duval","Polk","Brevard","Volusia","Lee","Sarasota"],
  GA: ["Fulton","Gwinnett","Cobb","DeKalb","Chatham","Clayton","Cherokee","Forsyth","Hall","Richmond"],
  HI: ["Honolulu","Maui","Hawaii","Kauai"],
  ID: ["Ada","Canyon","Kootenai","Twin Falls","Bannock","Bonneville","Nez Perce","Cassia","Madison","Bingham"],
  IL: ["Cook","DuPage","Lake","Will","Kane","McHenry","Winnebago","St. Clair","Champaign","Sangamon"],
  IN: ["Marion","Lake","Allen","Hamilton","Tippecanoe","St. Joseph","Hendricks","Elkhart","Johnson","Vanderburgh"],
  KS: ["Johnson","Sedgwick","Shawnee","Leavenworth","Wyandotte","Douglas","Riley","Butler","Reno","Saline"],
  KY: ["Jefferson","Fayette","Kenton","Boone","Warren","Hardin","Daviess","Campbell","McCracken","Christian"],
  ME: ["Cumberland","York","Penobscot","Kennebec","Androscoggin","Knox","Somerset","Aroostook","Oxford","Hancock"],
  MD: ["Montgomery","Prince George's","Baltimore","Anne Arundel","Howard","Frederick","Charles","Carroll","Harford","Baltimore City"],
  MA: ["Middlesex","Worcester","Essex","Suffolk","Norfolk","Bristol","Plymouth","Hampden","Hampshire","Barnstable"],
  MI: ["Oakland","Macomb","Washtenaw","Ingham","Kalamazoo","Ottawa","Kent","Genesee","Saginaw","Muskegon"],
  MN: ["Hennepin","Ramsey","Dakota","Anoka","Washington","Scott","Carver","St. Louis","Olmsted","Stearns"],
  MO: ["St. Louis","Jackson","St. Charles","Jefferson","Greene","Clay","Boone","Cass","St. Louis City","Franklin"],
  MT: ["Yellowstone","Cascade","Missoula","Gallatin","Flathead","Silver Bow","Ravalli","Cascade","Hill","Dawson"],
  NE: ["Douglas","Sarpy","Lancaster","Platte","Hall","Lincoln","Madison","Buffalo","Dodge","Scotts Bluff"],
  NV: ["Clark","Washoe","Carson City","Elko","Douglas","Lyon","Churchill","Humboldt","White Pine","Lander"],
  NH: ["Hillsborough","Rockingham","Merrimack","Cheshire","Strafford","Belknap","Sullivan","Carroll","Grafton","Coos"],
  NJ: ["Bergen","Middlesex","Essex","Hudson","Monmouth","Ocean","Union","Camden","Passaic","Morris"],
  NM: ["Bernalillo","Dona Ana","Santa Fe","Sandoval","San Juan","Chaves","Eddy","Lea","Otero","McKinley"],
  NY: ["Brooklyn","Queens","Bronx","Staten Island","Nassau","Suffolk","Westchester","Erie","Monroe","Onondaga"],
  NC: ["Mecklenburg","Wake","Guilford","Forsyth","Cumberland","Durham","Buncombe","Union","Cabarrus","Gaston"],
  ND: ["Cass","Burleigh","Grand Forks","Ward","Morton","Stark","Williams","Richland","Stutsman","Ramsey"],
  OH: ["Franklin","Cuyahoga","Hamilton","Summit","Montgomery","Lucas","Stark","Butler","Lorain","Mahoning"],
  OK: ["Tulsa","Canadian","Cleveland","Comanche","Garfield","Rogers","Washington","Creek","Payne","Pottawatomie"],
  OR: ["Multnomah","Washington","Clackamas","Lane","Marion","Jackson","Deschutes","Linn","Douglas","Yamhill"],
  PA: ["Philadelphia","Allegheny","Montgomery","Bucks","Chester","Delaware","York","Lancaster","Berks","Luzerne"],
  RI: ["Providence","Kent","Washington","Newport","Bristol"],
  SC: ["Greenville","Richland","Charleston","Horry","Spartanburg","Lexington","York","Anderson","Dorchester","Berkeley"],
  SD: ["Minnehaha","Pennington","Lincoln","Brown","Codington","Brookings","Meade","Lawrence","Roberts","Hughes"],
  TN: ["Shelby","Davidson","Knox","Hamilton","Rutherford","Williamson","Sullivan","Sumner","Maury","Montgomery"],
  TX: ["Dallas","Tarrant","Collin","Denton","Travis","Fort Bend","Montgomery","Williamson","Bexar","El Paso"],
  VT: ["Chittenden","Rutland","Windsor","Washington","Franklin","Addison","Orleans","Caledonia","Bennington","Windham"],
  VA: ["Fairfax","Prince William","Loudoun","Chesterfield","Henrico","Virginia Beach","Norfolk","Chesapeake","Arlington","Alexandria"],
  WA: ["King","Pierce","Snohomish","Spokane","Clark","Thurston","Kitsap","Whatcom","Benton","Yakima"],
  WV: ["Kanawha","Berkeley","Cabell","Monongalia","Putnam","Raleigh","Wood","Jefferson","Mercer","Marion"],
  WI: ["Milwaukee","Dane","Waukesha","Brown","Racine","Outagamie","Winnebago","Kenosha","Rock","Marathon"],
  WY: ["Laramie","Natrona","Campbell","Sweetwater","Uinta","Fremont","Teton","Park","Albany","Sheridan"],
  DC: ["Washington"],
  LA: ["East Baton Rouge","Calcasieu","Caddo","Jefferson","St. Tammany","Ouachita","Ascension","Terrebonne","Lafayette","Livingston"],
  MS: ["Hinds","Harrison","DeSoto","Rankin","Forrest","Lee","Jackson","Madison","Lamar","Jones"],
  PA_extra: [],
};

const clamp01 = (v: number) => Math.max(0, Math.min(100, v));

// Cache synthetic county names so getCountyFPIDetail can resolve them.
// Built lazily once per state on first access.
const SYNTHETIC_NAME_CACHE = new Map<string, string>();   // fips → name
const SYNTHETIC_POP_CACHE  = new Map<string, number>();   // fips → population

function ensureSyntheticCached(stateAbbr: string) {
  const stateInfo = US_STATES.find((s) => s.abbr === stateAbbr);
  if (!stateInfo) return;
  const key = `synth:${stateAbbr}:done`;
  if (SYNTHETIC_NAME_CACHE.has(key)) return;
  SYNTHETIC_NAME_CACHE.set(key, "");  // mark as cached
  const counties = syntheticCountiesForState(stateAbbr);
  counties.forEach((c) => {
    SYNTHETIC_NAME_CACHE.set(c.fips, c.name);
    SYNTHETIC_POP_CACHE.set(c.fips, c.population);
  });
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

  const center   = STATE_CENTROIDS[stateAbbr] ?? [39, -98];
  const rng      = rngFor(`synth:${stateAbbr}`);
  const realNames = REAL_COUNTY_NAMES[stateAbbr] ?? [];
  // Use 5-8 counties for states with real names, 4-5 for others
  const count    = realNames.length > 0 ? Math.min(realNames.length, intRange(rng, 5, 8)) : intRange(rng, 4, 6);

  const out: ReturnType<typeof syntheticCountiesForState> = [];
  for (let i = 0; i < count; i++) {
    const lat  = center[0] + (rng() - 0.5) * 3.5;
    const lng  = center[1] + (rng() - 0.5) * 4.5;
    const pop  = intRange(rng, 18_000, 600_000);
    const idx  = String(i + 1).padStart(3, "0");
    // Use real county name if available, otherwise "State County N"
    const name = realNames[i] ?? `${stateAbbr} County ${i + 1}`;
    out.push({
      fips: `${stateInfo.fips}${idx}`,
      stateAbbr,
      name,
      population: pop,
      centroid: [lat, lng],
    });
  }
  return out;
}

/** Build a CountyFPIDetail for any FIPS, using seeded data if available. */
export function getCountyFPIDetail(fips: string, stateAbbr: string, communityAdjustment = 0): CountyFPIDetail {
  ensureSyntheticCached(stateAbbr);
  const metrics = generateCountyMetrics(fips, stateAbbr);

  const seeded = ALL_COUNTIES.find((c) => c.fips === fips) as any;
  if (seeded?.components) {
    const c = seeded.components;
    metrics.alertSeverity       = { ...metrics.alertSeverity,  value: clamp01(c.shockExposure * 1.05) };
    metrics.drought             = { ...metrics.drought,         value: clamp01(c.shockExposure * 0.95) };
    metrics.poverty             = { ...metrics.poverty,         value: clamp01(c.vulnerability * 1.0) };
    metrics.foodInsecurity      = { ...metrics.foodInsecurity,  value: clamp01(c.vulnerability * 1.05) };
    metrics.foodAccess          = { ...metrics.foodAccess,      value: clamp01(c.supplyCapacity * 1.0) };
    metrics.stockShortfall      = { ...metrics.stockShortfall,  value: clamp01(c.supplyCapacity * 0.9) };
    metrics.voucherShortfall    = { ...metrics.voucherShortfall,value: clamp01(c.responseReadiness * 0.95) };
  }

  if (communityAdjustment !== 0) {
    const keys = Object.keys(metrics) as (keyof typeof metrics)[];
    keys.forEach((k) => {
      metrics[k] = { ...metrics[k], value: clamp01(metrics[k].value + communityAdjustment * 0.4) };
    });
  }

  const components = computeCountyComponents(metrics);
  const total      = computeCountyTotal(components);
  const trigger    = triggerForScore(total);
  const coverage   = coverageFromMetrics(metrics);

  return {
    fips,
    stateAbbr,
    name:       seeded?.name ?? SYNTHETIC_NAME_CACHE.get(fips) ?? `County ${fips}`,
    population: seeded?.population ?? SYNTHETIC_POP_CACHE.get(fips) ?? 50000,
    metrics,
    components,
    total,
    trigger,
    coverage,
    drivers: (seeded as any)?.drivers ?? [],
  };
}

/** Build a StateFPIDetail from all counties in a state. */
export function getStateFPIDetail(stateAbbr: string): StateFPIDetail {
  const stateInfo = US_STATES.find((s) => s.abbr === stateAbbr);
  const counties  = ALL_COUNTIES.filter((c) => c.stateAbbr === stateAbbr);
  const synthetic = syntheticCountiesForState(stateAbbr);

  const allFips = [
    ...counties.map((c) => c.fips),
    ...synthetic.map((c) => c.fips),
  ];

  const countyDetails = allFips.map((f) => getCountyFPIDetail(f, stateAbbr));
  const stateFPI      = computeStateFPI(countyDetails);

  return {
    stateAbbr,
    stateName:    stateInfo?.name ?? stateAbbr,
    ...stateFPI,
    countyCount:  countyDetails.length,
    asOf:         NOW_ISO,
  };
}