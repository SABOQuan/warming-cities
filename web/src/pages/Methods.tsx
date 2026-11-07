import { Fuzzy } from '../components/Fuzzy';
import type { CitiesIndex } from '../types';

const REPO = 'https://github.com/SABOQuan/warming-cities';

export function Methods({ index }: { index: CitiesIndex }) {
  const m = index.methodology;
  const [b0, b1] = m.baseline_period;

  return (
    <article className="prose">
      <Fuzzy as="h1" className="page-title" amount={0.28}>
        Methods
      </Fuzzy>
      <p className="meta">How the numbers on this site are made. Data as of {index.generated}.</p>

      <h2>Temperature</h2>
      <p>
        Each city uses one weather station from {m.sources.temperature}, the nearest one with a long
        record that is still reporting. Monthly means are averaged into annual means; a year needs
        enough months to count, and short years are flagged in the tables.
      </p>
      <dl className="defs">
        <dt>Anomaly</dt>
        <dd>
          A year&rsquo;s mean minus the station&rsquo;s {b0}–{b1} average. Each city is compared
          with itself, so a tropical city and a temperate one can sit on the same chart.
        </dd>
        <dt>Warming per decade</dt>
        <dd>
          An ordinary least-squares trend on annual means from {m.trend_start_year} on, with a 95%
          confidence interval.
        </dd>
        <dt>Rolling mean</dt>
        <dd>
          A centred {m.rolling_window_years}-year mean over calendar years. It needs 70% of the
          years in the window to be present.
        </dd>
        <dt>Unusually hot month</dt>
        <dd>{m.extreme_heat_month}</dd>
        <dt>Warming stripes</dt>
        <dd>
          One bar per year, coloured by anomaly and scaled to each city&rsquo;s own range, after Ed
          Hawkins&rsquo; <a href="https://showyourstripes.info">showyourstripes.info</a>. They show
          how each city changed, not how cities compare; use the compare view for that.
        </dd>
      </dl>

      <h2>Air quality</h2>
      <p>
        {m.sources.air_quality}, averaged across monitors into annual means. Monitor networks grow
        and change, so early years can rest on very few stations. The WHO annual guideline used here
        is {m.who_pm25_guideline} µg/m³ (2021 revision). Trends are only fitted when there are
        enough years.
      </p>

      <h2>What this is not</h2>
      <p>{m.caveat}</p>
      <p>
        A single station is not a whole city. Stations sit at airports and parks, and the urban heat
        island and station moves both leave a mark. The homogenized GHCN series corrects for the
        known breaks, not all of them.
      </p>

      <h2>Source code</h2>
      <p>
        Download, cleaning, analysis and export are a Python pipeline with tests; this site is a
        static React build that reads the exported JSON. Everything is at{' '}
        <a href={REPO}>{REPO.replace('https://', '')}</a>.
      </p>
    </article>
  );
}
