import type { CityData, CitySummary } from '../types';
import { fmt, signed } from './format';

export interface Entry extends CitySummary {
  /** Catalogue number: position in alphabetical order, stable whatever the current sort. */
  no: number;
}

export function catalogue(cities: CitySummary[]): Entry[] {
  return [...cities]
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((c, i) => ({ ...c, no: i + 1 }));
}

export const catNo = (no: number) => `No. ${String(no).padStart(2, '0')}`;

/** GHCN station names (NEW_DELHI_SAFDARJUN) as words (New Delhi Safdarjun). */
export const stationName = (s: string) =>
  s
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (ch) => ch.toUpperCase());

/** Two or three plain sentences about a city, built from its numbers. */
export function blurb(city: CityData, whoGuideline: number): string {
  const { station, stats } = city;
  const first = city.temperature[0]?.year;
  const trend = stats.temperature_trend;
  const pm = stats.pm25_trend;
  const parts: string[] = [];

  parts.push(
    `Readings from ${stationName(station.station_name)}, ${fmt(station.distance_km, 0)} km from the centre, go back to ${first}.`,
  );
  if (trend && stats.recent_anomaly_c !== null) {
    parts.push(
      `Since ${trend.first_year} it has warmed ${fmt(trend.per_decade_c)} °C a decade, and 2016–2025 ran ${signed(stats.recent_anomaly_c)} °C against 1961–1990.`,
    );
  }
  if (pm) {
    const multiple = pm.mean_pm25 / whoGuideline;
    let s = `PM2.5 has averaged ${fmt(pm.mean_pm25, 0)} µg/m³ since ${pm.first_year}, ${fmt(multiple, multiple < 10 ? 1 : 0)} times the WHO guideline`;
    if (
      pm.sufficient &&
      pm.pct_per_year !== undefined &&
      pm.p_value !== undefined &&
      pm.p_value < 0.05
    ) {
      s += `, ${pm.pct_per_year < 0 ? 'falling' : 'rising'} about ${fmt(Math.abs(pm.pct_per_year), 0)}% a year`;
    }
    parts.push(`${s}.`);
  }
  return parts.join(' ');
}
