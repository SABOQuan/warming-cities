// Colour is assigned by the job it does:
// - diverging (warmer / cooler than the baseline): ColorBrewer RdBu, neutral grey-white midpoint,
//   the palette Ed Hawkins uses for warming stripes;
// - categorical (which city, in compare mode): fixed order, never cycled, capped at 3 series
//   because crossing lines need every pair distinguishable (dataviz reference palette slots 1-3).

const RDBU = [
  '#053061',
  '#2166ac',
  '#4393c3',
  '#92c5de',
  '#d1e5f0',
  '#f7f7f7',
  '#fddbc7',
  '#f4a582',
  '#d6604d',
  '#b2182b',
  '#67001f',
];

/** Stripe colour for an anomaly, scaled symmetrically to ±limit (like showyourstripes.info). */
export function stripeColor(anomaly: number, limit: number): string {
  const t = Math.max(-1, Math.min(1, anomaly / (limit || 1)));
  const i = Math.round(((t + 1) / 2) * (RDBU.length - 1));
  return RDBU[i];
}

export const WARM = '#b2182b';
export const COOL = '#2166ac';

export const SERIES = ['#2a78d6', '#eb6834', '#1baf7a'] as const;
export const MAX_COMPARE = SERIES.length;
