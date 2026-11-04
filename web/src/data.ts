import { useEffect, useState } from 'react';
import type { CitiesIndex, CityData } from './types';

const DATA_URL = `${import.meta.env.BASE_URL}data`;

// Each file is fetched once per page load and shared between views (index, city, compare).
const cache = new Map<string, Promise<unknown>>();

function fetchJson<T>(path: string): Promise<T> {
  let hit = cache.get(path);
  if (!hit) {
    hit = fetch(`${DATA_URL}/${path}`).then((res) => {
      if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
      return res.json();
    });
    hit.catch(() => cache.delete(path));
    cache.set(path, hit);
  }
  return hit as Promise<T>;
}

export type Loadable<T> =
  { status: 'loading' } | { status: 'error'; error: string } | { status: 'ready'; data: T };

function useJson<T>(path: string | null): Loadable<T> {
  // Results are tagged with the path they belong to, so a stale result from a
  // previous path reads as 'loading' without a synchronous reset in the effect.
  const [result, setResult] = useState<{ path: string; value: Loadable<T> } | null>(null);

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    fetchJson<T>(path)
      .then((data) => !cancelled && setResult({ path, value: { status: 'ready', data } }))
      .catch(
        (err: unknown) =>
          !cancelled && setResult({ path, value: { status: 'error', error: String(err) } }),
      );
    return () => {
      cancelled = true;
    };
  }, [path]);

  return result !== null && result.path === path ? result.value : { status: 'loading' };
}

export const useCitiesIndex = () => useJson<CitiesIndex>('cities.json');

export const useCity = (id: string | null) => useJson<CityData>(id === null ? null : `${id}.json`);

/** Several cities at once; ready only when all of them are. */
export const useCities = (ids: string[]) => useMultiJson<CityData>(ids.map((id) => `${id}.json`));

function useMultiJson<T>(paths: string[]): Loadable<T[]> {
  const key = paths.join('|');
  const [result, setResult] = useState<{ key: string; value: Loadable<T[]> } | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all(key === '' ? [] : key.split('|').map((p) => fetchJson<T>(p)))
      .then((data) => !cancelled && setResult({ key, value: { status: 'ready', data } }))
      .catch(
        (err: unknown) =>
          !cancelled && setResult({ key, value: { status: 'error', error: String(err) } }),
      );
    return () => {
      cancelled = true;
    };
  }, [key]);

  return result !== null && result.key === key ? result.value : { status: 'loading' };
}
