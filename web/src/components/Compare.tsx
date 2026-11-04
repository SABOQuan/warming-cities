import { useState } from 'react';
import { useCities } from '../data';
import { MAX_COMPARE, SERIES } from '../lib/colors';
import { fmt, signed } from '../lib/format';
import type { Domain } from '../lib/scale';
import type { CitySummary } from '../types';
import { Chart } from './Chart';
import { YearRange } from './YearRange';

interface CompareProps {
  cities: CitySummary[];
  selected: string[];
  onChange: (ids: string[]) => void;
}

/** Give each selected city a colour slot, keeping slots it already has (colour follows the city). */
function assignSlots(selected: string[], previous: Record<string, number>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const id of selected) if (previous[id] !== undefined) out[id] = previous[id];
  const used = new Set(Object.values(out));
  for (const id of selected) {
    if (out[id] !== undefined) continue;
    const free = SERIES.findIndex((_, i) => !used.has(i));
    out[id] = free;
    used.add(free);
  }
  return out;
}

/**
 * Overlay of up to three cities' 10-year rolling anomalies. Rolling means, not raw annual values,
 * because three noisy annual series on one chart are unreadable. A city keeps its colour while it
 * stays selected; removing another city never repaints it.
 */
export function Compare({ cities, selected, onChange }: CompareProps) {
  const loaded = useCities(selected);
  const [range, setRange] = useState<Domain | null>(null);
  const [slotState, setSlotState] = useState<Record<string, number>>({});
  const slots = assignSlots(selected, slotState);

  const toggle = (id: string) => {
    const next = selected.includes(id)
      ? selected.filter((s) => s !== id)
      : selected.length < MAX_COMPARE
        ? [...selected, id]
        : selected;
    setSlotState(assignSlots(next, slots));
    onChange(next);
  };

  const names = new Map(cities.map((c) => [c.id, c.name]));
  const colorOf = new Map(selected.map((id) => [id, SERIES[slots[id]]]));

  let body = null;
  if (selected.length === 0) {
    body = <p className="muted">Pick up to {MAX_COMPARE} cities above.</p>;
  } else if (loaded.status === 'loading') {
    body = <p className="muted">Loading…</p>;
  } else if (loaded.status === 'error') {
    body = <p role="alert">{loaded.error}</p>;
  } else {
    const data = loaded.data;
    const bounds: Domain = [
      Math.min(...data.map((c) => c.temperature[0].year)),
      Math.max(...data.map((c) => c.temperature[c.temperature.length - 1].year)),
    ];
    const clamp = (r: Domain): Domain => [
      Math.max(bounds[0], Math.min(r[0], bounds[1] - 1)),
      Math.min(bounds[1], Math.max(r[1], bounds[0] + 1)),
    ];
    const shown = clamp(range ?? [1950, bounds[1]]);
    const lines = data.map((c) => ({
      id: c.id,
      label: c.name,
      color: colorOf.get(c.id) ?? SERIES[0],
      points: c.temperature.map((t) => ({
        x: t.year,
        y: t.rolling_c === null ? null : t.rolling_c - c.baseline.baseline_c,
      })),
    }));

    body = (
      <>
        <YearRange bounds={bounds} value={shown} onChange={setRange} />
        <ul className="legend" aria-label="Legend">
          {lines.map((l) => (
            <li key={l.id}>
              <span className="swatch" style={{ background: l.color }} /> {l.label}
            </li>
          ))}
        </ul>
        <Chart
          label={`10-year rolling temperature anomaly for ${lines.map((l) => l.label).join(', ')}`}
          xDomain={shown}
          lines={lines}
          directLabels={lines.length > 1}
          yFormat={(v) => `${signed(v, Number.isInteger(v) ? 0 : 1)}°`}
          tooltip={(year) => (
            <>
              <strong>{year} · 10-yr mean</strong>
              {lines.map((l) => {
                const p = l.points.find((q) => q.x === year);
                return (
                  <span key={l.id}>
                    <span style={{ color: l.color }}>●</span> {l.label}:{' '}
                    {p && p.y !== null ? `${signed(p.y)} °C` : 'no data'}
                  </span>
                );
              })}
            </>
          )}
        />
        <table className="compare-table">
          <thead>
            <tr>
              <th>City</th>
              <th>Warming since 1970</th>
              <th>2016–25 vs 1961–90</th>
              <th>Mean PM2.5</th>
            </tr>
          </thead>
          <tbody>
            {data.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{signed(c.stats.temperature_trend?.per_decade_c, 2)} °C / decade</td>
                <td>{signed(c.stats.recent_anomaly_c)} °C</td>
                <td>
                  {c.stats.pm25_trend ? `${fmt(c.stats.pm25_trend.mean_pm25, 1)} µg/m³` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </>
    );
  }

  return (
    <section className="compare">
      <fieldset className="compare-picker">
        <legend>
          Compare up to {MAX_COMPARE} cities ({selected.length} chosen)
        </legend>
        {cities.map((c) => {
          const on = selected.includes(c.id);
          return (
            <label key={c.id} className={on ? 'on' : undefined}>
              <input
                type="checkbox"
                checked={on}
                disabled={!on && selected.length >= MAX_COMPARE}
                onChange={() => toggle(c.id)}
              />
              {on && <span className="swatch" style={{ background: colorOf.get(c.id) }} />}
              {names.get(c.id)}
            </label>
          );
        })}
      </fieldset>
      {body}
    </section>
  );
}
