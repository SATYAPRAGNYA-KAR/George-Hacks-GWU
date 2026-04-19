// Deterministic pseudo-random helpers for stable baseline data per FIPS.
// Same seed → same value across reloads.

export function hash32(str: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

export function mulberry32(seed: number) {
  let t = seed >>> 0;
  return function () {
    t = (t + 0x6d2b79f5) >>> 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r = (r + Math.imul(r ^ (r >>> 7), 61 | r)) ^ r;
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

export function rngFor(key: string) {
  return mulberry32(hash32(key));
}

export function rangeRand(rng: () => number, min: number, max: number): number {
  return min + rng() * (max - min);
}

export function intRange(rng: () => number, min: number, max: number): number {
  return Math.floor(rangeRand(rng, min, max + 1));
}

/** Bias a 0-1 random toward `target` with given strength (0=no bias, 1=clamp to target). */
export function biasToward(r: number, target: number, strength = 0.5): number {
  return r * (1 - strength) + target * strength;
}
