// Tiny scale helpers for the hand-drawn SVG charts. No chart library: the charts are simple
// (bars + lines on one y-axis) and drawing them directly keeps full control of the styling.

export type Domain = [number, number];

/** Round tick step to 1, 2, 2.5 or 5 × a power of ten. */
function niceStep(span: number, count: number): number {
  const raw = span / Math.max(count, 1);
  const pow = 10 ** Math.floor(Math.log10(raw));
  const unit = raw / pow;
  const nice = unit <= 1 ? 1 : unit <= 2 ? 2 : unit <= 2.5 ? 2.5 : unit <= 5 ? 5 : 10;
  return nice * pow;
}

/** Expand [min, max] to whole tick steps and return the ticks inside it. */
export function niceTicks(
  min: number,
  max: number,
  count = 5,
): { domain: Domain; ticks: number[] } {
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const step = niceStep(max - min, count);
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Number(v.toFixed(10)));
  return { domain: [lo, hi], ticks };
}

/** Year ticks on round years, spaced so labels don't collide at the given width. */
export function yearTicks([x0, x1]: Domain, widthPx: number): number[] {
  const maxLabels = Math.max(2, Math.floor(widthPx / 64));
  const step = [1, 2, 5, 10, 20, 25, 50, 100].find((s) => (x1 - x0) / s <= maxLabels) ?? 100;
  const ticks: number[] = [];
  for (let y = Math.ceil(x0 / step) * step; y <= x1; y += step) ticks.push(y);
  return ticks;
}

export const linear =
  ([d0, d1]: Domain, [r0, r1]: Domain) =>
  (v: number) =>
    d1 === d0 ? r0 : r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
