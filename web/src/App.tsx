import { Compare } from './components/Compare';
import { Fuzzy } from './components/Fuzzy';
import { useCitiesIndex } from './data';
import { catalogue } from './lib/catalog';
import { signed } from './lib/format';
import { City } from './pages/City';
import { Home } from './pages/Home';
import { Methods } from './pages/Methods';
import { href, replaceHash, useRoute, type Route } from './router';
import type { CitiesIndex } from './types';

const DEFAULT_COMPARE = ['london', 'delhi', 'sao_paulo'];

/** A slow ticker of each city's 2016-25 anomaly, the way a 2001 portal ran stock prices. */
function Ticker({ index }: { index: CitiesIndex }) {
  const items = (copy: string) =>
    catalogue(index.cities).map((c) => (
      <span key={`${copy}-${c.id}`} className="ticker-item">
        {c.name.toUpperCase()} <b>{signed(c.recent_anomaly_c)} °C</b>
      </span>
    ));
  return (
    <div className="ticker" aria-hidden="true">
      <div className="ticker-track">
        {items('a')}
        {items('b')}
      </div>
    </div>
  );
}

function Nav({ route }: { route: Route }) {
  const links: [string, string, Route['page']][] = [
    ['index', href.index, 'index'],
    ['compare', href.compare(), 'compare'],
    ['methods', href.methods, 'methods'],
  ];
  return (
    <nav className="nav" aria-label="Site">
      {links.map(([label, to, page]) => (
        <a key={page} href={to} aria-current={route.page === page ? 'page' : undefined}>
          {label}
        </a>
      ))}
    </nav>
  );
}

function Page({ route, index }: { route: Route; index: CitiesIndex }) {
  switch (route.page) {
    case 'city':
      return <City id={route.id} index={index} />;
    case 'compare': {
      const known = new Set(index.cities.map((c) => c.id));
      const ids = (route.ids ?? DEFAULT_COMPARE).filter((id) => known.has(id));
      const [b0, b1] = index.methodology.baseline_period;
      return (
        <article>
          <Fuzzy as="h1" className="page-title" amount={0.28}>
            Compare
          </Fuzzy>
          <p className="block-lede">
            Ten-year rolling means against each city&rsquo;s own {b0}–{b1} average, so the lines
            show how much each place has changed, not which one is hotter.
          </p>
          <Compare
            cities={catalogue(index.cities)}
            selected={ids}
            onChange={(next) => replaceHash(href.compare(next))}
          />
        </article>
      );
    }
    case 'methods':
      return <Methods index={index} />;
    default:
      return <Home index={index} />;
  }
}

export default function App() {
  const route = useRoute();
  const index = useCitiesIndex();

  return (
    <div className="site">
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="masthead">
        {index.status === 'ready' && <Ticker index={index.data} />}
        <a href={href.index} className="wordmark-link" aria-label="Warming Cities, home">
          <Fuzzy as="span" className="wordmark" amount={0.32}>
            Warming Cities
          </Fuzzy>
        </a>
        <p className="tagline">
          temperature &amp; air in eleven cities, from the first readings to 2025
        </p>
        <Nav route={route} />
      </header>

      <main id="main">
        {index.status === 'loading' && <p className="loading">Loading&hellip;</p>}
        {index.status === 'error' && <p role="alert">{index.error}</p>}
        {index.status === 'ready' && <Page route={route} index={index.data} />}
      </main>

      <footer className="colophon">
        <p className="divider" aria-hidden="true">
          * &nbsp; * &nbsp; *
        </p>
        {index.status === 'ready' && (
          <p>
            Temperature: {index.data.methodology.sources.temperature}. Air quality:{' '}
            {index.data.methodology.sources.air_quality}. Data generated {index.data.generated}.
          </p>
        )}
        <p>
          &copy; Warming Cities 2026. Temperature and PM2.5 are shown side by side, not as cause and
          effect. <a href={href.methods}>How it&rsquo;s made</a>.
        </p>
      </footer>
    </div>
  );
}
