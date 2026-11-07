import { useEffect, useState } from 'react';

// Hash routes, so the static build works on any host without rewrite rules:
//   #/                     index
//   #/city/<id>            one city
//   #/compare?c=<id>,<id>  comparison
//   #/methods              how the numbers are made

export type Route =
  | { page: 'index' }
  | { page: 'city'; id: string }
  | { page: 'compare'; ids: string[] | null }
  | { page: 'methods' };

export function parseHash(hash: string): Route {
  const [path, query = ''] = hash.replace(/^#/, '').split('?');
  const parts = path.split('/').filter(Boolean);
  if (parts[0] === 'city' && parts[1]) return { page: 'city', id: decodeURIComponent(parts[1]) };
  if (parts[0] === 'compare') {
    const c = new URLSearchParams(query).get('c');
    return { page: 'compare', ids: c === null ? null : c.split(',').filter(Boolean) };
  }
  if (parts[0] === 'methods') return { page: 'methods' };
  return { page: 'index' };
}

export const href = {
  index: '#/',
  city: (id: string) => `#/city/${encodeURIComponent(id)}`,
  compare: (ids?: string[]) => (ids ? `#/compare?c=${ids.join(',')}` : '#/compare'),
  methods: '#/methods',
};

/** Swap the URL without adding a history entry (for filter-like state such as compare picks). */
export function replaceHash(hash: string) {
  history.replaceState(null, '', hash);
  window.dispatchEvent(new HashChangeEvent('hashchange'));
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  // New page (or another city) starts at the top; filter changes within a page don't jump.
  const pageKey = route.page === 'city' ? `city:${route.id}` : route.page;
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pageKey]);

  return route;
}
