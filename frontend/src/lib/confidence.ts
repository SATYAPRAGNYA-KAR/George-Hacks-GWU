// Community Incident Confidence engine.
// Inputs: cluster of community signal reports.
// Output: confidence band + confidence score + capped FPI adjustment.

import type {
  CommunitySignalReport,
  IncidentSignalCluster,
  SignalConfidence,
} from "@/types/foodready";

const MAX_FPI_ADJ = 5; // capped influence on county FPI

interface ScoreCluster {
  reports: CommunitySignalReport[];
  officialCorroboration: boolean;
}

function uniqueReporterCount(reports: CommunitySignalReport[]): number {
  return new Set(reports.map((r) => r.reporterFingerprint)).size;
}

function geoCluster(reports: CommunitySignalReport[]): number {
  // ZIP-level proxy: more reports sharing ZIP → higher cluster
  if (reports.length < 2) return 0;
  const zips = new Map<string, number>();
  reports.forEach((r) => zips.set(r.zip, (zips.get(r.zip) || 0) + 1));
  const max = Math.max(...zips.values());
  return Math.min(1, max / Math.max(2, reports.length));
}

function timeCluster(reports: CommunitySignalReport[]): number {
  if (reports.length < 2) return 0;
  const times = reports.map((r) => new Date(r.createdAt).getTime()).sort((a, b) => a - b);
  const span = times[times.length - 1] - times[0];
  // Tighter span = stronger cluster. <2h → 1.0, >24h → 0.
  const hours = span / 3_600_000;
  if (hours <= 2) return 1;
  if (hours >= 24) return 0;
  return 1 - (hours - 2) / 22;
}

function evidenceScore(reports: CommunitySignalReport[]): number {
  const withEvidence = reports.filter((r) => r.imageUrl || r.householdsAffectedEstimate).length;
  return reports.length === 0 ? 0 : withEvidence / reports.length;
}

function consistencyScore(reports: CommunitySignalReport[]): number {
  if (reports.length === 0) return 0;
  // Severity & category consistency
  const cats = new Set(reports.map((r) => r.category)).size;
  const sevs = new Set(reports.map((r) => r.severity)).size;
  const catScore = 1 / cats;
  const sevScore = Math.max(0, 1 - (sevs - 1) * 0.25);
  return (catScore + sevScore) / 2;
}

export function scoreCluster(c: ScoreCluster): {
  confidenceScore: number;
  confidence: SignalConfidence;
  fpiAdjustment: number;
  breakdown: {
    reportCount: number;
    uniqueReporters: number;
    geo: number;
    time: number;
    evidence: number;
    consistency: number;
    official: boolean;
  };
} {
  const reportCount = c.reports.length;
  const unique = uniqueReporterCount(c.reports);
  const geo = geoCluster(c.reports);
  const time = timeCluster(c.reports);
  const evidence = evidenceScore(c.reports);
  const consistency = consistencyScore(c.reports);

  // Weighted composite (0-100)
  const reportPart = Math.min(1, reportCount / 8) * 18;     // diminishing
  const uniquePart = Math.min(1, unique / 5) * 18;          // unique reporters more important
  const geoPart = geo * 14;
  const timePart = time * 12;
  const evidencePart = evidence * 14;
  const consistencyPart = consistency * 12;
  const officialPart = c.officialCorroboration ? 12 : 0;

  const confidenceScore = Math.round(
    reportPart + uniquePart + geoPart + timePart + evidencePart + consistencyPart + officialPart,
  );

  let confidence: SignalConfidence = "unverified";
  if (c.officialCorroboration) {
    confidence = "officially_corroborated";
  } else if (confidenceScore >= 70) {
    confidence = "probable";
  } else if (confidenceScore >= 45) {
    confidence = "probable";
  }
  // coordinator_verified is set explicitly via store action

  // Capped FPI adjustment: confidence drives 0-MAX_FPI_ADJ
  const adj = (confidenceScore / 100) * MAX_FPI_ADJ;
  const fpiAdjustment = Math.round(adj * 10) / 10;

  return {
    confidenceScore,
    confidence,
    fpiAdjustment,
    breakdown: {
      reportCount,
      uniqueReporters: unique,
      geo: Math.round(geo * 100) / 100,
      time: Math.round(time * 100) / 100,
      evidence: Math.round(evidence * 100) / 100,
      consistency: Math.round(consistency * 100) / 100,
      official: c.officialCorroboration,
    },
  };
}

/** Group raw reports into clusters by (countyFips + category). */
export function clusterReports(
  reports: CommunitySignalReport[],
  officiallyCorroboratedKeys: Set<string>,
): IncidentSignalCluster[] {
  const groups = new Map<string, CommunitySignalReport[]>();
  reports.forEach((r) => {
    const key = `${r.countyFips}::${r.category}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(r);
  });

  const clusters: IncidentSignalCluster[] = [];
  groups.forEach((items, key) => {
    const [countyFips, category] = key.split("::");
    const official = officiallyCorroboratedKeys.has(key);
    const scored = scoreCluster({ reports: items, officialCorroboration: official });
    items.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
    clusters.push({
      id: `cluster-${key}`,
      countyFips,
      category: category as any,
      reportIds: items.map((i) => i.id),
      uniqueReporters: scored.breakdown.uniqueReporters,
      geoClusterScore: scored.breakdown.geo,
      timeClusterScore: scored.breakdown.time,
      evidenceScore: scored.breakdown.evidence,
      consistencyScore: scored.breakdown.consistency,
      officialCorroboration: scored.breakdown.official,
      confidence: scored.confidence,
      confidenceScore: scored.confidenceScore,
      fpiAdjustment: scored.fpiAdjustment,
      firstReportAt: items[0].createdAt,
      lastReportAt: items[items.length - 1].createdAt,
    });
  });

  return clusters;
}
