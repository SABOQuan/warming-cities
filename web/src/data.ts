import { useEffect, useState } from 'react';
import type { CitiesIndex, CityData } from './types';

const DATA_URL = `${import.meta.env.BASE_URL}data`;

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${DATA_URL}/${path}`);
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return (await res.json()) as T;
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
