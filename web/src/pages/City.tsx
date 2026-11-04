import { useState } from 'react';
import { Pm25Chart, TemperatureChart } from '../components/CityCharts';
import { Fuzzy } from '../components/Fuzzy';
import { Stripes } from '../components/Stripes';
import { YearRange } from '../components/YearRange';
import { useCity } from '../data';
import { catNo, catalogue, stationName } from '../lib/catalog';
import { fmt, signed } from '../lib/format';
import type { Domain } from '../lib/scale';
import { href } from '../router';
import type { CitiesIndex, CityData } from '../types';

function CityBody({ city, index }: { city: CityData; index: CitiesIndex }) {
  const years = city.temperature.map((t) => t.year);
  const bounds: Domain = [years[0], years[years.length - 1]];
  const [range, setRange] = useState<Domain>(bounds);

  const entries = catalogue(index.cities);
  const at = entries.findIndex((e) => e.id === city.id);
  const prev = entries[(at - 1 + entries.length) % entries.length];
  const next = entries[(at + 1) % entries.length];

  const { stats, station, baseline } = city;
  const trend = stats.temperature_trend;
  const pm = stats.pm25_trend;
  const corr = stats.temp_pm25_correlation;
  const guideline = index.methodology.who_pm25_guideline;
  const [b0, b1] = baseline.period;
  const warmest = city.warmest_years[0];
  const hotMonths = city.extreme_heat
    .filter((h) => h.year >= 2016)
    .reduce((n, h) => n + h.hot_months, 0);

  return (
    <article className="city">
      <p className="meta crumbs">
        <a href={href.index}>&larr; index</a> &nbsp;·&nbsp; {catNo(entries[at].no)} &nbsp;·&nbsp;{' '}
        {fmt(city.lat, 2)}°, {fmt(city.lon, 2)}°
      </p>
      <Fuzzy as="h1" className="city-title" amount={0.3}>
        {city.name}
      </Fuzzy>
      <p className="city-station">
        Station: {stationName(station.station_name)} ({station.station_id}),{' '}
        {fmt(station.distance_km, 1)} km from the city centre. Baseline {b0}–{b1}:{' '}
        {fmt(baseline.baseline_c, 1)} °C.
      </p>

      <figure className="banner">
        <Stripes
          temperature={city.temperature}
          height={120}
          label={`Warming stripes for ${city.name}, ${bounds[0]}–${bounds[1]}`}
        />
        <figcaption className="meta">
          <span>{bounds[0]}</span>
          <span>
            one stripe per year, against {b0}–{b1}
          </span>
          <span>{bounds[1]}</span>
        </figcaption>
      </figure>

      <dl className="figures">
        <div>
          <dt>
            2016–2025 vs {b0}–{b1}
          </dt>
          <dd>{signed(stats.recent_anomaly_c)} °C</dd>
        </div>
        {trend && (
          <div>
            <dt>Trend since {trend.first_year}</dt>
            <dd>{signed(trend.per_decade_c)} °C</dd>
            <dd className="figure-note">
              per decade, 95% CI {fmt(trend.ci95_low_c)} to {fmt(trend.ci95_high_c)}
            </dd>
          </div>
        )}
        {warmest && (
          <div>
            <dt>Warmest year</dt>
            <dd>{warmest.year}</dd>
            <dd className="figure-note">{signed(warmest.anomaly_c)} °C</dd>
          </div>
        )}
        <div>
          <dt>Mean PM2.5</dt>
          <dd>{pm ? `${fmt(pm.mean_pm25, 0)} µg/m³` : '—'}</dd>
          {pm && (
            <dd className="figure-note">
              {fmt(pm.mean_pm25 / guideline, 1)}× WHO, {pm.first_year}–{pm.last_year}
            </dd>
          )}
        </div>
      </dl>

      <section className="block" aria-labelledby="t-temp">
        <h2 id="t-temp" className="block-title">
          Temperature
        </h2>
        <p className="block-lede">
          Each bar is one year&rsquo;s mean against the {b0}–{b1} average; the black line is the
          10-year rolling mean. Since 2016 there have been {hotMonths} unusually hot months (more
          than two standard deviations above normal for that month).
        </p>
        <YearRange bounds={bounds} value={range} onChange={setRange} />
        <TemperatureChart city={city} range={range} />
        <details className="table-toggle">
          <summary>View as table</summary>
          <table>
            <thead>
              <tr>
                <th>Year</th>
                <th>Mean °C</th>
                <th>Anomaly °C</th>
                <th>10-yr mean anomaly °C</th>
                <th>Months</th>
              </tr>
            </thead>
            <tbody>
              {city.temperature
                .filter((t) => t.year >= range[0] && t.year <= range[1])
                .map((t) => (
                  <tr key={t.year}>
                    <td>{t.year}</td>
                    <td>{fmt(t.temp_c)}</td>
                    <td>{signed(t.anomaly_c)}</td>
                    <td>{signed(t.rolling_c)}</td>
                    <td>{t.n_months}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </details>

        <div className="two-col">
          <div>
            <h3 className="minor-title">Warmest years</h3>
            <ol className="ranked">
              {city.warmest_years.map((w) => (
                <li key={w.year}>
                  <span>{w.year}</span> <span>{signed(w.anomaly_c)} °C</span>
                </li>
              ))}
            </ol>
          </div>
          <div>
            <h3 className="minor-title">By decade</h3>
            <table className="decades">
              <tbody>
                {city.decades.map((d) => (
                  <tr key={d.decade}>
                    <td>{d.decade}s</td>
                    <td>{signed(d.anomaly_c)} °C</td>
                    <td className="muted">{d.n_years < 10 ? `${d.n_years} yrs` : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="block" aria-labelledby="t-air">
        <h2 id="t-air" className="block-title">
          Air quality
        </h2>
        {city.air_quality.length === 0 ? (
          <p className="block-lede">No reference-monitor PM2.5 data for this city.</p>
        ) : (
          <>
            <p className="block-lede">
              Annual mean PM2.5 from reference monitors (OpenAQ). The dashed line is the WHO annual
              guideline of {guideline} µg/m³. The record is short, so read the trend loosely.
              {pm?.sufficient &&
                pm.pct_per_year !== undefined &&
                ` Fitted trend: ${signed(pm.pct_per_year, 1)}% a year${pm.p_value !== undefined && pm.p_value >= 0.05 ? ' (not statistically clear)' : ''}.`}
            </p>
            <Pm25Chart city={city} guideline={guideline} />
            <details className="table-toggle">
              <summary>View as table</summary>
              <table>
                <thead>
                  <tr>
                    <th>Year</th>
                    <th>PM2.5 µg/m³</th>
                    <th>× WHO</th>
                    <th>Monitors</th>
                    <th>Months</th>
                  </tr>
                </thead>
                <tbody>
                  {city.air_quality.map((a) => (
                    <tr key={a.year}>
                      <td>{a.year}</td>
                      <td>{fmt(a.pm25, 1)}</td>
                      <td>{fmt(a.who_multiple, 1)}</td>
                      <td>{a.n_locations}</td>
                      <td>{a.n_months}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
            {corr && corr.r !== null && (
              <p className="aside">
                Hotter years and dirtier years? Over {corr.n_years} years the correlation is r ={' '}
                {fmt(corr.r)}, and {fmt(corr.r_detrended)} once both trends are removed. Too few
                years to say much, and they would not be cause and effect anyway.
              </p>
            )}
          </>
        )}
      </section>

      {city.notes.length > 0 && (
        <section className="block" aria-labelledby="t-notes">
          <h2 id="t-notes" className="block-title">
            Notes on this record
          </h2>
          <ul className="notes">
            {city.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </section>
      )}

      <nav className="pager" aria-label="More cities">
        <a href={href.city(prev.id)}>
          <span className="meta">&larr; previous</span>
          {prev.name}
        </a>
        <a href={href.compare([city.id, next.id])} className="pager-mid">
          <span className="meta">compare</span>
          side by side
        </a>
        <a href={href.city(next.id)} className="pager-next">
          <span className="meta">next &rarr;</span>
          {next.name}
        </a>
      </nav>
    </article>
  );
}

export function City({ id, index }: { id: string; index: CitiesIndex }) {
  const city = useCity(id);
  if (!index.cities.some((c) => c.id === id))
    return (
      <p className="empty">
        No city called &ldquo;{id}&rdquo;. <a href={href.index}>Back to the index</a>.
      </p>
    );
  if (city.status === 'loading') return <p className="loading">Loading&hellip;</p>;
  if (city.status === 'error') return <p role="alert">{city.error}</p>;
  return <CityBody key={city.data.id} city={city.data} index={index} />;
}
