// Legacy compatibility shim — risk.ts now delegates to lib/fpi.ts.
// Existing imports of computeTotalScore / triggerForScore / TRIGGER_META / colorForScore continue to work.

import type { ComponentScores, TriggerLevel } from "@/types/foodready";
import {
  COUNTY_DOMAIN_WEIGHTS,
  computeCountyTotal,
  triggerForScore as triggerForScoreFpi,
  TRIGGER_META as TRIGGER_META_FPI,
  colorForScore as colorForScoreFpi,
  TRIGGER_THRESHOLDS as TRIGGER_THRESHOLDS_FPI,
} from "@/lib/fpi";

export const COMPONENT_WEIGHTS = COUNTY_DOMAIN_WEIGHTS;

export function computeTotalScore(c: ComponentScores, weights = COUNTY_DOMAIN_WEIGHTS): number {
  return computeCountyTotal(c, weights);
}

export function triggerForScore(score: number): TriggerLevel {
  return triggerForScoreFpi(score);
}

export const TRIGGER_THRESHOLDS = {
  prepared: [0, TRIGGER_THRESHOLDS_FPI.watch - 1] as [number, number],
  watch: [TRIGGER_THRESHOLDS_FPI.watch, TRIGGER_THRESHOLDS_FPI.warning - 1] as [number, number],
  warning: [TRIGGER_THRESHOLDS_FPI.warning, TRIGGER_THRESHOLDS_FPI.action - 1] as [number, number],
  action: [TRIGGER_THRESHOLDS_FPI.action, TRIGGER_THRESHOLDS_FPI.critical - 1] as [number, number],
  critical: [TRIGGER_THRESHOLDS_FPI.critical, 100] as [number, number],
};

export const TRIGGER_META: Record<
  TriggerLevel,
  { label: string; color: string; cssVar: string; description: string; actions: string[] }
> = Object.fromEntries(
  Object.entries(TRIGGER_META_FPI).map(([k, v]) => [
    k,
    { ...v, color: `hsl(var(${v.cssVar}))` },
  ]),
) as any;

export function colorForScore(score: number): string {
  return colorForScoreFpi(score);
}

export function generateReference(): string {
  const seg = () => Math.random().toString(36).slice(2, 6).toUpperCase();
  return `FR-${seg()}-${seg()}`;
}
