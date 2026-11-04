import { stripeColor } from '../lib/colors';
import type { TemperatureYear } from '../types';

interface StripesProps {
  temperature: TemperatureYear[];
  height?: number;
  label: string;
}

/**
 * Warming stripes: one bar per year, coloured by its anomaly against the 1961-1990 baseline.
 * Colours are scaled to this city's own largest anomaly, like showyourstripes.info, so stripes
 * show each city's own change rather than compare cities. Missing years stay blank.
 */
export function Stripes({ temperature, height = 80, label }: StripesProps) {
  if (temperature.length === 0) return null;
  const first = temperature[0].year;
  const last = temperature[temperature.length - 1].year;
  const limit = Math.max(...temperature.map((t) => Math.abs(t.anomaly_c)));

  return (
    <svg
      className="stripes"
      viewBox={`${first} 0 ${last - first + 1} 1`}
      preserveAspectRatio="none"
      height={height}
      role="img"
      aria-label={label}
    >
      {temperature.map((t) => (
        <rect
          key={t.year}
          x={t.year}
          y={0}
          width={1.04}
          height={1}
          fill={stripeColor(t.anomaly_c, limit)}
        >
          <title>
            {t.year}: {t.anomaly_c >= 0 ? '+' : ''}
            {t.anomaly_c.toFixed(2)} °C
          </title>
        </rect>
      ))}
    </svg>
  );
}
