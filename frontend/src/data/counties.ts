import type { County, ComponentScores } from "@/types/foodready";
import { computeTotalScore, triggerForScore } from "@/lib/risk";

// Iowa: rich seeded data — 25 counties with varied risk profiles.
// Approx centroids [lat, lng] for Leaflet markers (county boundary geojson skipped for MVP simplicity).
export interface IowaCountySeed extends County {
  centroid: [number, number];
  components: ComponentScores;
  drivers: { label: string; value: number; category: "shock" | "vulnerability" | "supply" | "readiness" }[];
}

const mk = (
  fips: string,
  name: string,
  pop: number,
  centroid: [number, number],
  c: ComponentScores,
  drivers: IowaCountySeed["drivers"],
): IowaCountySeed => ({
  fips, stateAbbr: "IA", name, population: pop, seedRich: true, centroid,
  components: c, drivers,
});

export const IOWA_COUNTIES: IowaCountySeed[] = [
  // High-risk seeded: Appanoose, Wapello, Cass, Crawford
  mk("19007", "Appanoose", 12300, [40.74, -92.87],
    { shockExposure: 78, vulnerability: 82, supplyCapacity: 70, responseReadiness: 65 },
    [
      { label: "Persistent rural poverty", value: 84, category: "vulnerability" },
      { label: "Pantry density below state avg", value: 72, category: "supply" },
      { label: "NWS flood watch active", value: 76, category: "shock" },
    ]),
  mk("19179", "Wapello", 35400, [41.03, -92.41],
    { shockExposure: 72, vulnerability: 78, supplyCapacity: 66, responseReadiness: 60 },
    [
      { label: "Child food insecurity 22%", value: 80, category: "vulnerability" },
      { label: "Recent grocery price spike", value: 70, category: "supply" },
      { label: "Heavy rainfall anomaly", value: 68, category: "shock" },
    ]),
  mk("19029", "Cass", 12700, [41.33, -94.93],
    { shockExposure: 68, vulnerability: 74, supplyCapacity: 72, responseReadiness: 70 },
    [
      { label: "Rural pantry coverage gap", value: 76, category: "supply" },
      { label: "Aging population, mobility limits", value: 72, category: "vulnerability" },
      { label: "Derecho recovery still active", value: 70, category: "shock" },
    ]),
  mk("19047", "Crawford", 16500, [42.04, -95.38],
    { shockExposure: 66, vulnerability: 72, supplyCapacity: 68, responseReadiness: 64 },
    [
      { label: "Meatpacking workforce vulnerability", value: 75, category: "vulnerability" },
      { label: "Limited responder capacity", value: 70, category: "readiness" },
      { label: "Drought-stressed vegetation (NDVI)", value: 64, category: "shock" },
    ]),
  // Mid-risk
  mk("19153", "Polk", 492400, [41.69, -93.57],
    { shockExposure: 42, vulnerability: 38, supplyCapacity: 28, responseReadiness: 24 },
    [
      { label: "Strong responder network (Des Moines)", value: 22, category: "readiness" },
      { label: "Urban food bank coverage", value: 28, category: "supply" },
    ]),
  mk("19113", "Linn", 226000, [42.08, -91.6],
    { shockExposure: 48, vulnerability: 42, supplyCapacity: 36, responseReadiness: 30 },
    [
      { label: "Cedar Rapids derecho legacy risk", value: 52, category: "shock" },
      { label: "Strong food bank presence", value: 32, category: "supply" },
    ]),
  mk("19163", "Scott", 174000, [41.63, -90.62],
    { shockExposure: 44, vulnerability: 46, supplyCapacity: 40, responseReadiness: 36 },
    []),
  mk("19103", "Johnson", 153000, [41.67, -91.59],
    { shockExposure: 38, vulnerability: 32, supplyCapacity: 26, responseReadiness: 22 },
    []),
  mk("19013", "Black Hawk", 131000, [42.47, -92.31],
    { shockExposure: 50, vulnerability: 56, supplyCapacity: 44, responseReadiness: 40 },
    [{ label: "Refugee/immigrant food access gap", value: 60, category: "vulnerability" }]),
  mk("19193", "Woodbury", 103000, [42.39, -96.05],
    { shockExposure: 56, vulnerability: 60, supplyCapacity: 52, responseReadiness: 48 },
    []),
  mk("19061", "Dubuque", 97000, [42.47, -90.88],
    { shockExposure: 46, vulnerability: 44, supplyCapacity: 38, responseReadiness: 34 },
    []),
  mk("19169", "Story", 98000, [42.04, -93.46],
    { shockExposure: 36, vulnerability: 30, supplyCapacity: 28, responseReadiness: 24 },
    []),
  mk("19127", "Marshall", 39800, [42.04, -92.99],
    { shockExposure: 62, vulnerability: 64, supplyCapacity: 56, responseReadiness: 52 },
    [{ label: "2020 derecho lingering vulnerability", value: 66, category: "shock" }]),
  mk("19139", "Muscatine", 42300, [41.48, -91.11],
    { shockExposure: 44, vulnerability: 48, supplyCapacity: 42, responseReadiness: 38 },
    []),
  mk("19167", "Sioux", 35900, [43.08, -96.18],
    { shockExposure: 38, vulnerability: 34, supplyCapacity: 32, responseReadiness: 30 },
    []),
  mk("19015", "Boone", 26300, [42.04, -93.93],
    { shockExposure: 40, vulnerability: 42, supplyCapacity: 38, responseReadiness: 36 },
    []),
  mk("19045", "Clinton", 46400, [41.9, -90.53],
    { shockExposure: 50, vulnerability: 54, supplyCapacity: 48, responseReadiness: 44 },
    []),
  mk("19057", "Des Moines", 38800, [40.92, -91.18],
    { shockExposure: 54, vulnerability: 60, supplyCapacity: 52, responseReadiness: 48 },
    [{ label: "Mississippi flood exposure", value: 60, category: "shock" }]),
  mk("19087", "Henry", 19900, [40.99, -91.54],
    { shockExposure: 42, vulnerability: 50, supplyCapacity: 46, responseReadiness: 42 },
    []),
  mk("19105", "Jones", 20400, [42.12, -91.13],
    { shockExposure: 36, vulnerability: 38, supplyCapacity: 36, responseReadiness: 34 },
    []),
  mk("19011", "Benton", 25500, [42.08, -92.07],
    { shockExposure: 38, vulnerability: 40, supplyCapacity: 38, responseReadiness: 36 },
    []),
  mk("19017", "Bremer", 24500, [42.78, -92.32],
    { shockExposure: 32, vulnerability: 30, supplyCapacity: 30, responseReadiness: 28 },
    []),
  mk("19171", "Tama", 16700, [42.08, -92.53],
    { shockExposure: 50, vulnerability: 56, supplyCapacity: 54, responseReadiness: 50 },
    []),
  mk("19035", "Cherokee", 11200, [42.74, -95.62],
    { shockExposure: 44, vulnerability: 46, supplyCapacity: 50, responseReadiness: 48 },
    []),
  mk("19071", "Fremont", 6800, [40.74, -95.6],
    { shockExposure: 70, vulnerability: 64, supplyCapacity: 62, responseReadiness: 56 },
    [{ label: "Missouri River flood risk", value: 78, category: "shock" }]),
];

export function iowaCountyToScore(c: IowaCountySeed) {
  const total = computeTotalScore(c.components);
  return { total, level: triggerForScore(total) };
}

// Lighter sample data: ~3 counties for a few other states to prove national scalability.
export interface SampleCounty extends County {
  centroid: [number, number];
  components: ComponentScores;
}

const sc = (fips: string, abbr: string, name: string, pop: number, centroid: [number, number], c: ComponentScores): SampleCounty =>
  ({ fips, stateAbbr: abbr, name, population: pop, seedRich: false, centroid, components: c });

export const SAMPLE_COUNTIES: SampleCounty[] = [
  // Texas
  sc("48201", "TX", "Harris", 4731000, [29.86, -95.39], { shockExposure: 62, vulnerability: 56, supplyCapacity: 40, responseReadiness: 32 }),
  sc("48029", "TX", "Bexar", 2009000, [29.45, -98.52], { shockExposure: 48, vulnerability: 52, supplyCapacity: 38, responseReadiness: 34 }),
  sc("48141", "TX", "El Paso", 865000, [31.85, -106.43], { shockExposure: 56, vulnerability: 64, supplyCapacity: 48, responseReadiness: 42 }),
  // California
  sc("06037", "CA", "Los Angeles", 9829000, [34.05, -118.25], { shockExposure: 50, vulnerability: 60, supplyCapacity: 36, responseReadiness: 28 }),
  sc("06019", "CA", "Fresno", 1009000, [36.74, -119.79], { shockExposure: 64, vulnerability: 70, supplyCapacity: 54, responseReadiness: 46 }),
  sc("06107", "CA", "Tulare", 477000, [36.21, -118.78], { shockExposure: 68, vulnerability: 76, supplyCapacity: 60, responseReadiness: 54 }),
  // Florida
  sc("12086", "FL", "Miami-Dade", 2674000, [25.76, -80.19], { shockExposure: 70, vulnerability: 58, supplyCapacity: 38, responseReadiness: 30 }),
  sc("12057", "FL", "Hillsborough", 1483000, [27.95, -82.46], { shockExposure: 64, vulnerability: 50, supplyCapacity: 36, responseReadiness: 28 }),
  // Louisiana
  sc("22071", "LA", "Orleans", 376000, [29.95, -90.07], { shockExposure: 78, vulnerability: 72, supplyCapacity: 56, responseReadiness: 50 }),
  sc("22051", "LA", "Jefferson", 432000, [29.86, -90.11], { shockExposure: 72, vulnerability: 60, supplyCapacity: 48, responseReadiness: 42 }),
  // Mississippi
  sc("28049", "MS", "Hinds", 222000, [32.27, -90.44], { shockExposure: 60, vulnerability: 78, supplyCapacity: 62, responseReadiness: 58 }),
  // Kentucky (rural Appalachia)
  sc("21195", "KY", "Pike", 56000, [37.47, -82.4], { shockExposure: 66, vulnerability: 80, supplyCapacity: 70, responseReadiness: 64 }),
  // West Virginia
  sc("54109", "WV", "Wyoming", 20000, [37.6, -81.55], { shockExposure: 58, vulnerability: 82, supplyCapacity: 72, responseReadiness: 68 }),
  // Oklahoma
  sc("40109", "OK", "Oklahoma", 798000, [35.51, -97.51], { shockExposure: 56, vulnerability: 54, supplyCapacity: 42, responseReadiness: 36 }),
  // North Dakota
  sc("38101", "ND", "Ward", 67000, [48.23, -101.55], { shockExposure: 48, vulnerability: 40, supplyCapacity: 50, responseReadiness: 46 }),
  // Arizona
  sc("04019", "AZ", "Pima", 1057000, [32.13, -110.95], { shockExposure: 58, vulnerability: 56, supplyCapacity: 44, responseReadiness: 38 }),
  // New York
  sc("36061", "NY", "New York (Manhattan)", 1628000, [40.78, -73.97], { shockExposure: 38, vulnerability: 50, supplyCapacity: 28, responseReadiness: 22 }),
  // Michigan
  sc("26163", "MI", "Wayne (Detroit)", 1750000, [42.33, -83.05], { shockExposure: 44, vulnerability: 68, supplyCapacity: 50, responseReadiness: 40 }),
];

// All counties combined (for lookups)
export const ALL_COUNTIES: (IowaCountySeed | SampleCounty)[] = [...IOWA_COUNTIES, ...SAMPLE_COUNTIES];
