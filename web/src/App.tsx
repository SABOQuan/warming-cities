import { useState } from 'react';
import { useCitiesIndex, useCity } from './data';
import type { CitiesIndex, CityData } from './types';

// Phase 4: unstyled on purpose. This proves the pipeline -> JSON -> app wiring
// end to end; charts come in Phase 5 and the visual design in Phase 7.

const fmt = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined ? '—' : v.toFixed(digits);

function CityDetail({ city }: { city: CityData }) {
  const { stats } = city;
  const trend = stats.temperature_trend;
  const pm = stats.pm25_trend;
  const corr = stats.temp_pm25_correlation;

  return (
    <article>
      <h2>{city.name}</h2>
      <p>
        Station: {city.station.station_name} ({city.station.station_id}), {city.station.distance_km}{' '}
        km from the city centre. Baseline {city.baseline.period.join('–')}:{' '}
        {fmt(city.baseline.baseline_c)} °C.
      </p>

      <h3>Stats</h3>
      <ul>
        <li>Recent anomaly: {fmt(stats.recent_anomaly_c)} °C</li>
        {trend && (
          <li>
            Warming trend {trend.first_year}–{trend.last_year}: {fmt(trend.per_decade_c, 3)}{' '}
            °C/decade (95% CI {fmt(trend.ci95_low_c, 3)} to {fmt(trend.ci95_high_c, 3)})
          </li>
        )}
        {pm && (
          <li>
            PM2.5 {pm.first_year}–{pm.last_year}: mean {fmt(pm.mean_pm25, 1)} µg/m³
            {pm.sufficient && `, ${fmt(pm.pct_per_year, 1)}% per year`}
          </li>
        )}
        {corr && (
          <li>
            Temp vs PM2.5 correlation: r = {fmt(corr.r)} (detrended {fmt(corr.r_detrended)}), n ={' '}
            {corr.n_years}
          </li>
        )}
      </ul>

      {city.notes.length > 0 && (
        <>
          <h3>Notes</h3>
          <ul>
            {city.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      )}

      <h3>Warmest years</h3>
      <ol>
        {city.warmest_years.map((w) => (
          <li key={w.year}>
            {w.year}: +{fmt(w.anomaly_c)} °C
          </li>
        ))}
      </ol>

      <h3>Annual temperature ({city.temperature.length} years)</h3>
      <table>
        <thead>
          <tr>
            <th>Year</th>
            <th>Mean °C</th>
            <th>Anomaly °C</th>
            <th>10-yr rolling °C</th>
          </tr>
        </thead>
        <tbody>
          {city.temperature.map((t) => (
            <tr key={t.year}>
              <td>{t.year}</td>
              <td>{fmt(t.temp_c)}</td>
              <td>{fmt(t.anomaly_c)}</td>
              <td>{fmt(t.rolling_c)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Annual PM2.5 ({city.air_quality.length} years)</h3>
      <table>
        <thead>
          <tr>
            <th>Year</th>
            <th>PM2.5 µg/m³</th>
            <th>× WHO guideline</th>
            <th>Monitors</th>
          </tr>
        </thead>
        <tbody>
          {city.air_quality.map((a) => (
            <tr key={a.year}>
              <td>{a.year}</td>
              <td>{fmt(a.pm25, 1)}</td>
              <td>{fmt(a.who_multiple, 1)}</td>
              <td>{a.n_locations}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </article>
  );
}

function CityView({ id }: { id: string }) {
  const city = useCity(id);
  if (city.status === 'loading') return <p>Loading city…</p>;
  if (city.status === 'error') return <p role="alert">{city.error}</p>;
  return <CityDetail city={city.data} />;
}

function Explorer({ index }: { index: CitiesIndex }) {
  const [selected, setSelected] = useState(index.cities[0]?.id ?? null);
  const { methodology } = index;

  return (
    <>
      <label>
        City:{' '}
        <select value={selected ?? ''} onChange={(e) => setSelected(e.target.value)}>
          {index.cities.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>

      {selected && <CityView id={selected} />}

      <footer>
        <p>{methodology.caveat}</p>
        <p>
          Sources: {methodology.sources.temperature}; {methodology.sources.air_quality}. Data
          generated {index.generated}.
        </p>
      </footer>
    </>
  );
}

export default function App() {
  const index = useCitiesIndex();

  return (
    <main>
      <h1>Warming Cities</h1>
      {index.status === 'loading' && <p>Loading…</p>}
      {index.status === 'error' && <p role="alert">{index.error}</p>}
      {index.status === 'ready' && <Explorer index={index.data} />}
    </main>
  );
}
