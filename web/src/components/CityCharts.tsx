import { COOL, WARM } from '../lib/colors';
import { fmt, signed } from '../lib/format';
import type { Domain } from '../lib/scale';
import type { CityData } from '../types';
import { Chart } from './Chart';

const INK = '#111';
const PM_FILL = '#6f7f8f';

/** Annual anomaly bars (warm/cool against the baseline) with the 10-year rolling mean on top. */
export function TemperatureChart({ city, range }: { city: CityData; range: Domain }) {
  const byYear = new Map(city.temperature.map((t) => [t.year, t]));
  const [b0, b1] = city.baseline.period;

  return (
    <Chart
      label={`${city.name}: annual temperature anomaly against ${b0}–${b1}, with a 10-year rolling mean`}
      xDomain={range}
      bars={city.temperature.map((t) => ({
        x: t.year,
        y: t.anomaly_c,
        color: t.anomaly_c >= 0 ? WARM : COOL,
      }))}
      lines={[
        {
          id: 'rolling',
          label: '10-yr mean',
          color: INK,
          points: city.temperature.map((t) => ({
            x: t.year,
            y: t.rolling_c,
          })),
        },
      ]}
      yFormat={(v) => `${signed(v, Number.isInteger(v) ? 0 : 1)}°`}
      tooltip={(year) => {
        const t = byYear.get(year);
        if (!t) return <span className="tip-muted">{year}: no data</span>;
        return (
          <>
            <strong>{year}</strong>
            <span>
              {fmt(t.temp_c, 1)} °C mean, {signed(t.anomaly_c)} °C vs {b0}–{b1}
            </span>
            {t.rolling_c !== null && <span>10-yr mean: {signed(t.rolling_c)} °C</span>}
            {t.n_months < 12 && <span className="tip-muted">{t.n_months}/12 months observed</span>}
          </>
        );
      }}
    />
  );
}

/** Annual mean PM2.5 against the WHO annual guideline. */
export function Pm25Chart({ city, guideline }: { city: CityData; guideline: number }) {
  const aq = city.air_quality;
  if (aq.length === 0) return null;
  const byYear = new Map(aq.map((a) => [a.year, a]));

  return (
    <Chart
      label={`${city.name}: annual mean PM2.5 against the WHO guideline of ${guideline} µg/m³`}
      xDomain={[aq[0].year, aq[aq.length - 1].year]}
      bars={aq.map((a) => ({ x: a.year, y: a.pm25, color: PM_FILL }))}
      refLines={[{ y: guideline, label: 'WHO guideline' }]}
      yFormat={(v) => String(v)}
      height={220}
      tooltip={(year) => {
        const a = byYear.get(year);
        if (!a) return <span className="tip-muted">{year}: no data</span>;
        return (
          <>
            <strong>{year}</strong>
            <span>
              {fmt(a.pm25, 1)} µg/m³ ({fmt(a.who_multiple, 1)}× WHO)
            </span>
            <span className="tip-muted">
              {a.n_locations} monitor{a.n_locations === 1 ? '' : 's'}, {a.n_months} months
            </span>
          </>
        );
      }}
    />
  );
}
