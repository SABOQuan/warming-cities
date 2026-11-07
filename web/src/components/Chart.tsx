import { useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { linear, niceTicks, yearTicks, type Domain } from '../lib/scale';

export interface Point {
  x: number;
  y: number | null;
}

export interface LineSeries {
  id: string;
  label: string;
  color: string;
  points: Point[];
}

export interface Bar {
  x: number;
  y: number;
  color: string;
}

export interface RefLine {
  y: number;
  label: string;
}

interface ChartProps {
  label: string;
  xDomain: Domain;
  bars?: Bar[];
  lines?: LineSeries[];
  refLines?: RefLine[];
  yFormat: (v: number) => string;
  /** Write each line's label at its right end (used when there are 2+ lines). */
  directLabels?: boolean;
  height?: number;
  tooltip: (year: number) => ReactNode | null;
}

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

/** One continuous path per run of non-null points, so data gaps stay visible as gaps. */
function linePath(points: Point[], x: (v: number) => number, y: (v: number) => number): string {
  let d = '';
  let open = false;
  let prevX: number | null = null;
  for (const p of points) {
    if (p.y === null || (prevX !== null && p.x - prevX > 1)) open = false;
    if (p.y !== null) {
      d += `${open ? 'L' : 'M'}${x(p.x).toFixed(1)},${y(p.y).toFixed(1)}`;
      open = true;
    }
    prevX = p.x;
  }
  return d;
}

/** Push end-of-line labels apart vertically so close lines don't print on top of each other. */
function spreadLabels<T extends { py: number }>(labels: T[], minGap = 14): T[] {
  const sorted = [...labels].sort((a, b) => a.py - b.py);
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].py - sorted[i - 1].py < minGap)
      sorted[i] = { ...sorted[i], py: sorted[i - 1].py + minGap };
  }
  return sorted;
}

export function Chart({
  label,
  xDomain,
  bars = [],
  lines = [],
  refLines = [],
  yFormat,
  directLabels = false,
  height = 280,
  tooltip,
}: ChartProps) {
  const [wrapRef, width] = useWidth();
  const [hover, setHover] = useState<number | null>(null);

  const [x0, x1] = xDomain;
  const inRange = (x: number) => x >= x0 && x <= x1;
  const visibleBars = bars.filter((b) => inRange(b.x));
  const visibleLines = lines.map((l) => ({ ...l, points: l.points.filter((p) => inRange(p.x)) }));

  const values = [
    0,
    ...visibleBars.map((b) => b.y),
    ...visibleLines.flatMap((l) => l.points.map((p) => p.y).filter((v): v is number => v !== null)),
    ...refLines.map((r) => r.y),
  ];
  const { domain: yDomain, ticks } = niceTicks(Math.min(...values), Math.max(...values), 5);

  // Right margin holds direct labels or reference-line labels, so they never sit on the data.
  const right = directLabels ? 96 : refLines.length > 0 ? 92 : 12;
  const m = { top: 10, right, bottom: 24, left: 44 };
  const plotW = Math.max(40, width - m.left - m.right);
  const plotH = height - m.top - m.bottom;
  const band = plotW / (x1 - x0 + 1);
  const x = (year: number) => m.left + (year - x0 + 0.5) * band;
  const y = linear(yDomain, [m.top + plotH, m.top]);
  const gap = band > 4 ? 1 : 0;
  const barW = Math.min(28, Math.max(0.5, band - gap));

  const yearAt = (px: number) =>
    Math.max(x0, Math.min(x1, Math.round(x0 + (px - m.left) / band - 0.5)));

  const onKey = (e: KeyboardEvent) => {
    const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (step === 0) return;
    e.preventDefault();
    setHover((h) => Math.max(x0, Math.min(x1, (h ?? (step > 0 ? x0 - 1 : x1 + 1)) + step)));
  };

  const tip = hover !== null ? tooltip(hover) : null;
  const tipLeft = hover !== null && x(hover) > width / 2;

  return (
    <div className="chart" ref={wrapRef}>
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={label}
        tabIndex={0}
        onPointerMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          setHover(yearAt(e.clientX - rect.left));
        }}
        onPointerLeave={() => setHover(null)}
        onBlur={() => setHover(null)}
        onKeyDown={onKey}
      >
        <g className="chart-grid">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={m.left} x2={m.left + plotW} y1={y(t)} y2={y(t)} />
              <text x={m.left - 6} y={y(t)} dy="0.32em" textAnchor="end">
                {yFormat(t)}
              </text>
            </g>
          ))}
        </g>
        <g className="chart-axis">
          <line x1={m.left} x2={m.left + plotW} y1={y(0)} y2={y(0)} className="chart-zero" />
          {yearTicks(xDomain, plotW).map((t) => (
            <text key={t} x={x(t)} y={height - 6} textAnchor="middle">
              {t}
            </text>
          ))}
        </g>

        {visibleBars.map((b) => {
          const top = Math.min(y(b.y), y(0));
          return (
            <rect
              key={b.x}
              x={x(b.x) - barW / 2}
              width={barW}
              y={top}
              height={Math.max(0.5, Math.abs(y(b.y) - y(0)))}
              fill={b.color}
              opacity={hover === null || hover === b.x ? 1 : 0.55}
            />
          );
        })}

        {refLines.map((r) => (
          <g key={r.label} className="chart-ref">
            <line x1={m.left} x2={m.left + plotW} y1={y(r.y)} y2={y(r.y)} />
            <text x={m.left + plotW + 6} y={y(r.y)} dy="0.32em">
              {r.label}
            </text>
          </g>
        ))}

        {visibleLines.map((l) => (
          <path key={l.id} d={linePath(l.points, x, y)} stroke={l.color} className="chart-line" />
        ))}

        {directLabels &&
          spreadLabels(
            visibleLines.flatMap((l) => {
              const last = [...l.points].reverse().find((p) => p.y !== null);
              return last && last.y !== null ? [{ line: l, px: x(last.x), py: y(last.y) }] : [];
            }),
          ).map(({ line, px, py }) => (
            <text key={line.id} x={px + 8} y={py} dy="0.32em" className="chart-direct-label">
              <tspan fill={line.color}>●</tspan> {line.label}
            </text>
          ))}

        {hover !== null && (
          <g className="chart-hover">
            <line x1={x(hover)} x2={x(hover)} y1={m.top} y2={m.top + plotH} />
            {visibleLines.map((l) => {
              const p = l.points.find((q) => q.x === hover);
              return p && p.y !== null ? (
                <circle key={l.id} cx={x(hover)} cy={y(p.y)} r={4} fill={l.color} />
              ) : null;
            })}
          </g>
        )}
      </svg>

      {tip && hover !== null && (
        <div
          className="chart-tip"
          role="status"
          style={{
            top: m.top,
            left: tipLeft ? undefined : x(hover) + 12,
            right: tipLeft ? width - x(hover) + 12 : undefined,
          }}
        >
          {tip}
        </div>
      )}
    </div>
  );
}
