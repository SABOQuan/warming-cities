import { useState } from 'react';
import { Fuzzy } from '../components/Fuzzy';
import { Stripes } from '../components/Stripes';
import { useCities } from '../data';
import { blurb, catNo, catalogue, type Entry } from '../lib/catalog';
import { fmt, signed } from '../lib/format';
import { href } from '../router';
import type { CitiesIndex, CityData } from '../types';

type SortKey = 'name' | 'warming' | 'recent' | 'pm25' | 'record';

const SORTS: { key: SortKey; label: string; value: (e: Entry) => number | string | null }[] = [
  { key: 'name', label: 'Name', value: (e) => e.name },
  { key: 'warming', label: 'Warming per decade', value: (e) => e.warming_per_decade_c },
  { key: 'recent', label: '2016–25 anomaly', value: (e) => e.recent_anomaly_c },
  { key: 'pm25', label: 'Mean PM2.5', value: (e) => e.mean_pm25 },
  { key: 'record', label: 'Length of record', value: (e) => e.temperature_years[0] },
];

function median(values: number[]) {
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

function sortEntries(entries: Entry[], key: SortKey, desc: boolean) {
  const get = SORTS.find((s) => s.key === key)!.value;
  return [...entries].sort((a, b) => {
    const va = get(a);
    const vb = get(b);
    if (va === null) return 1; // missing values always last
    if (vb === null) return -1;
    const cmp = typeof va === 'string' ? va.localeCompare(String(vb)) : va - Number(vb);
    return desc ? -cmp : cmp;
  });
}

function CityEntry({
  entry,
  data,
  guideline,
}: {
  entry: Entry;
  data?: CityData;
  guideline: number;
}) {
  const [hot, setHot] = useState(false);
  const [first, last] = entry.temperature_years;

  return (
    <article className="entry">
      <a
        className="entry-link"
        href={href.city(entry.id)}
        onPointerEnter={() => setHot(true)}
        onPointerLeave={() => setHot(false)}
        onFocus={() => setHot(true)}
        onBlur={() => setHot(false)}
      >
        <span className="meta">
          {catNo(entry.no)} &nbsp;·&nbsp; {first}–{last} &nbsp;·&nbsp; {last - first + 1} yrs
        </span>
        <div className="entry-stripes">
          {data ? (
            <Stripes
              temperature={data.temperature}
              height={44}
              label={`Warming stripes, ${entry.name}`}
            />
          ) : (
            <div className="stripes-placeholder" />
          )}
        </div>
        <Fuzzy as="h3" className="entry-title" amount={0.26} active={hot}>
          {entry.name}
        </Fuzzy>
        <p className="entry-blurb">{data ? blurb(data, guideline) : ' '}</p>
        <dl className="entry-figures">
          <div>
            <dt>2016–25</dt>
            <dd>{signed(entry.recent_anomaly_c)} °C</dd>
          </div>
          <div>
            <dt>per decade</dt>
            <dd>{signed(entry.warming_per_decade_c)} °C</dd>
          </div>
          <div>
            <dt>PM2.5</dt>
            <dd>{entry.mean_pm25 === null ? '—' : `${fmt(entry.mean_pm25, 0)} µg/m³`}</dd>
          </div>
        </dl>
        <span className="read-more">Read more &rarr;</span>
      </a>
    </article>
  );
}

export function Home({ index }: { index: CitiesIndex }) {
  const entries = catalogue(index.cities);
  const all = useCities(entries.map((e) => e.id));
  const byId = new Map<string, CityData>(
    all.status === 'ready' ? all.data.map((c) => [c.id, c]) : [],
  );

  const [keyword, setKeyword] = useState('');
  const [sort, setSort] = useState<SortKey>('name');
  const [desc, setDesc] = useState(false);

  const q = keyword.trim().toLowerCase();
  const shown = sortEntries(
    entries.filter((e) => q === '' || e.name.toLowerCase().includes(q)),
    sort,
    desc,
  );

  const anomalies = entries.map((e) => e.recent_anomaly_c).filter((v): v is number => v !== null);
  const warmer = anomalies.filter((v) => v > 0).length;
  const { baseline_period: bp } = index.methodology;

  return (
    <>
      <section className="intro">
        <p className="intro-lede">
          Eleven cities, one long-running weather station each, and every year on record. Each thin
          bar in the stripes below is a year: blue is cooler than that city&rsquo;s{' '}
          <span className="nw">{`${bp[0]}–${bp[1]}`}</span> average, red is warmer.
        </p>
        <div className="hero-figure">
          <Fuzzy as="p" className="hero-number" amount={0.24}>
            {signed(median(anomalies), 1)} °C
          </Fuzzy>
          <p className="hero-caption">
            How much warmer the typical city here was in <span className="nw">2016–2025</span> than
            in <span className="nw">{`${bp[0]}–${bp[1]}`}</span>. {warmer} of {anomalies.length}{' '}
            cities are warmer.
          </p>
        </div>
      </section>

      <section className="index" aria-labelledby="index-title">
        <h2 id="index-title" className="section-title">
          Index of Cities
        </h2>

        <form className="panel" onSubmit={(e) => e.preventDefault()} role="search">
          <p className="panel-title">Search and sort by&hellip;</p>
          <div className="panel-row">
            <label className="field">
              <span>Keyword</span>
              <input
                type="search"
                value={keyword}
                placeholder="lahore, sydney, etc."
                onChange={(e) => setKeyword(e.target.value)}
              />
            </label>
            <label className="field">
              <span>Sort by</span>
              <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
                {SORTS.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Order</span>
              <select
                value={desc ? 'desc' : 'asc'}
                onChange={(e) => setDesc(e.target.value === 'desc')}
              >
                <option value="asc">Ascending</option>
                <option value="desc">Descending</option>
              </select>
            </label>
            <button
              type="button"
              className="gel"
              onClick={() => {
                setKeyword('');
                setSort('name');
                setDesc(false);
              }}
            >
              Reset filters
            </button>
          </div>
          <p className="panel-count" aria-live="polite">
            Showing {shown.length} of {entries.length}
          </p>
        </form>

        <p className="divider" aria-hidden="true">
          * &nbsp; * &nbsp; *
        </p>

        {all.status === 'error' && <p role="alert">{all.error}</p>}
        {shown.length === 0 ? (
          <p className="empty">No city matches &ldquo;{keyword}&rdquo;.</p>
        ) : (
          <div className="feed">
            {shown.map((e) => (
              <CityEntry
                key={e.id}
                entry={e}
                data={byId.get(e.id)}
                guideline={index.methodology.who_pm25_guideline}
              />
            ))}
          </div>
        )}
      </section>
    </>
  );
}
