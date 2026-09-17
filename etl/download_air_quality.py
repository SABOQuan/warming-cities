"""Phase 1 — raw data acquisition.

Currently implements the OpenAQ (air quality) leg only. NOAA GHCN-Monthly (temperature) and
PSMSL (sea level, coastal cities) land here later as sibling functions — see ROADMAP.md Phase 1.

OpenAQ v3 has no "city" endpoint (that existed in v2 and was removed). A `location` is one physical
monitoring station. So for each city we do a radius search around its coordinates to find every
station nearby, then download each station's PM2.5 sensor readings separately. Phase 2 (clean.py)
is where those per-station series get averaged into one city-level annual number.

Three reliability lessons baked in below, all found by running this against the real API:

1. A single request spanning many years of measurements can time out server-side (HTTP 408)
   partway through, silently truncating a station's history. Fixed by requesting one calendar
   year at a time instead of one multi-year range.
2. A long unattended run (10 cities, potentially hours) can outlast the machine staying awake or
   the network staying up. A transient failure used to just skip that station forever. Fixed with
   retries (exponential backoff) for transient errors, and with resumability: each station's output
   file records whether its download actually completed, so a second run of the same command skips
   what's already done and only retries what failed or is missing — don't disable sleep and babysit
   the terminal, just rerun the command until every city reports complete.
3. OpenAQ enforces TWO rate limits at once — 60 requests/minute AND 2,000 requests/hour — and
   breaching either repeatedly gets the API key suspended (it then fails every request with 401,
   not 429). Pacing requests to stay under 60/min is not enough on its own: a run sustained for a
   full hour at close to 60/min blows through the hourly cap long before the minute-by-minute rate
   ever looks like a problem. See RATE_LIMIT_SLEEP_S below for the math. On top of that, a 401
   means the key itself is dead — retrying it or moving on to the next city just sends more
   requests to a key that's already suspended, so it's treated as fatal (see _request_json and
   main below) instead of being retried like a transient error.

Usage:
    python download_air_quality.py                # all 10 cities, safe to rerun/resumes
    python download_air_quality.py --city lahore  # just one, for testing
    python download_air_quality.py --from 2018-01-01 --to 2024-12-31
    python download_air_quality.py --overwrite     # ignore existing files, re-download everything
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

from cities import CITIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


class ApiKeyRejected(RuntimeError):
    """Raised when OpenAQ returns 401 — the key is missing/invalid/suspended, not a transient
    error. Retrying or moving on to the next city would just send more requests to a dead key,
    so this propagates all the way up and stops the whole run (see main())."""

BASE_URL = "https://api.openaq.org/v3"
PM25_PARAMETER_ID = 2  # OpenAQ's fixed id for PM2.5 — see /v3/parameters
RADIUS_M = 25_000  # meters; 25km is the max radius v3 accepts per request
PAGE_LIMIT = 100  # locations per page
MEASUREMENTS_PAGE_LIMIT = 1000
REQUEST_TIMEOUT_S = 15
# OpenAQ free tier caps at 60 req/min AND 2,000 req/hour — the hourly cap is the binding one for a
# long sustained run like this script does. 2,000/hour = 33.3 req/min average, so pace at 1.85s
# between requests: 60 / 1.85 ≈ 32.4 req/min sustained ≈ 1,946 req/hour, under the cap with a
# margin. (1.1s, the old value, sustains ≈54 req/min ≈ 3,272 req/hour — 64% over the hourly limit —
# which is what got the API key suspended.)
RATE_LIMIT_SLEEP_S = 1.85
RETRY_ATTEMPTS = 4
RETRY_BACKOFF_BASE_S = 5  # sleeps 5s, 10s, 20s between the 4 attempts

RAW_DIR = Path(__file__).parent / "data" / "raw" / "openaq"


def get_session() -> requests.Session:
    """Build a requests session carrying the OpenAQ API key from etl/.env."""
    load_dotenv()
    api_key = os.environ.get("OPENAQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAQ_API_KEY is not set. Copy etl/.env.example to etl/.env and fill it in "
            "(sign up free at https://explore.openaq.org)."
        )
    session = requests.Session()
    session.headers.update({"X-API-Key": api_key})
    return session


def _request_json(session: requests.Session, url: str, params: dict, what: str) -> dict | None:
    """GET url, retrying transient failures with exponential backoff.

    Returns the parsed JSON body, or None if every attempt failed (network down, DNS broken,
    persistent 5xx/408). None is the "give up on this one request" signal — callers decide
    whether that means stop paginating, skip a year, or skip a station.

    401 is NOT treated as one of those transient failures — it means the API key itself is
    missing/invalid/suspended, so no number of retries will ever succeed. It's raised immediately
    as ApiKeyRejected instead of being retried (see class docstring).

    429 (rate limited) gets special handling too: instead of the generic fixed backoff, it reads
    how long OpenAQ says to wait (Retry-After, falling back to x-ratelimit-reset) and sleeps
    exactly that long, so we resume right when the window actually opens instead of guessing.
    """
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
            if resp.status_code == 401:
                raise ApiKeyRejected(
                    f"OpenAQ rejected the API key (401) on {what}. The key is missing, invalid, "
                    "or has been suspended — check etl/.env and your OpenAQ account."
                )
            resp.raise_for_status()
            return resp.json()
        except ApiKeyRejected:
            raise  # fatal — let it propagate past the retry loop, not just this function
        except requests.exceptions.RequestException as exc:
            is_last_attempt = attempt == RETRY_ATTEMPTS
            if is_last_attempt:
                log.warning("%s failed after %d attempts: %s", what, RETRY_ATTEMPTS, exc)
                return None

            if getattr(exc.response, "status_code", None) == 429:
                # Rate-limited: trust the server's own timer over our fixed backoff schedule.
                retry_after = exc.response.headers.get("Retry-After") or exc.response.headers.get(
                    "x-ratelimit-reset"
                )
                if retry_after:
                    backoff = float(retry_after)
                else:
                    backoff = RETRY_BACKOFF_BASE_S * (2 ** (attempt - 1))
            else:
                backoff = RETRY_BACKOFF_BASE_S * (2 ** (attempt - 1))

            log.warning(
                "%s failed (attempt %d/%d): %s — retrying in %ds",
                what, attempt, RETRY_ATTEMPTS, exc, backoff,
            )
            time.sleep(backoff)
    return None  # unreachable, satisfies type checkers


def _year_chunks(date_from: str, date_to: str) -> list[tuple[str, str]]:
    """Split an ISO date range into calendar-year-bounded (start, end) pairs.

    Keeps each API request small enough that it doesn't hit OpenAQ's server-side timeout on
    a busy station's full multi-year history (see module docstring, lesson 1).
    """
    start_year = int(date_from[:4])
    end_year = int(date_to[:4])
    chunks = []
    for year in range(start_year, end_year + 1):
        chunk_start = date_from if year == start_year else f"{year}-01-01"
        chunk_end = date_to if year == end_year else f"{year}-12-31"
        chunks.append((chunk_start, chunk_end))
    return chunks


def fetch_locations(
    session: requests.Session,
    lat: float,
    lon: float,
    radius: int = RADIUS_M,
    monitors_only: bool = True,
) -> list[dict]:
    """Return PM2.5-capable stations within `radius` meters of (lat, lon).

    monitors_only=True (default) keeps only reference-grade government monitors
    (location["isMonitor"] is True) and drops low-cost community sensor nodes
    (PurpleAir/AirGradient/Clarity/etc). Verified against Lahore: of 84 stations within
    25km, 83 were low-cost nodes with zero measurements in a test window and 1 was the
    reference monitor with 618 — averaging in the empty low-cost nodes would silently
    bias nothing (they contribute no readings) but downloading all 84 wastes ~80 requests
    per city for no data. Set False if a city turns out to have no reference monitor and
    you want to fall back to low-cost sensors instead.

    Returns an empty list — rather than raising — on network failure or when nothing is
    found nearby, so a bad city coordinate or a transient outage doesn't take down the
    whole run.
    """
    locations: list[dict] = []
    page = 1
    while True:
        payload = _request_json(
            session,
            f"{BASE_URL}/locations",
            {
                "coordinates": f"{lat},{lon}",
                "radius": radius,
                "parameters_id": PM25_PARAMETER_ID,
                "limit": PAGE_LIMIT,
                "page": page,
            },
            what=f"locations request for ({lat}, {lon}) page {page}",
        )
        if payload is None:
            break

        results = payload.get("results", [])
        locations.extend(results)

        # See the identical comment in fetch_measurements — meta.found can be a
        # non-numeric string (">100"), so a short page is the only safe stop signal.
        if len(results) < PAGE_LIMIT:
            break
        page += 1
        time.sleep(RATE_LIMIT_SLEEP_S)  # pace every request, not just ones between stations/cities

    if monitors_only:
        kept = [loc for loc in locations if loc.get("isMonitor")]
        if not kept and locations:
            log.warning(
                "no reference monitors within %dm of (%s, %s), only %d low-cost sensor(s) — "
                "falling back to those",
                radius, lat, lon, len(locations),
            )
            kept = locations
        locations = kept

    if not locations:
        log.warning("no stations found within %dm of (%s, %s)", radius, lat, lon)
    return locations


def fetch_measurements(
    session: requests.Session, sensor_id: int, date_from: str, date_to: str
) -> tuple[list[dict], bool]:
    """Pull all measurements for one sensor between date_from and date_to (YYYY-MM-DD).

    Requests one calendar year at a time (see module docstring, lesson 1). Returns
    (measurements, complete) — complete is False if any year's request exhausted its
    retries, so the caller knows this station's data is partial and should be retried
    on a future run rather than treated as done.
    """
    measurements: list[dict] = []
    complete = True

    for chunk_from, chunk_to in _year_chunks(date_from, date_to):
        page = 1
        while True:
            payload = _request_json(
                session,
                f"{BASE_URL}/sensors/{sensor_id}/measurements",
                {
                    "datetime_from": chunk_from,
                    "datetime_to": chunk_to,
                    "limit": MEASUREMENTS_PAGE_LIMIT,
                    "page": page,
                },
                what=f"measurements for sensor {sensor_id}, {chunk_from}..{chunk_to} page {page}",
            )
            if payload is None:
                complete = False
                break

            results = payload.get("results", [])
            measurements.extend(results)

            # Stop once a page comes back short of the limit — that's the last page.
            # Do NOT use meta.found for this: OpenAQ returns it as the literal string
            # ">1000" once the true count exceeds the page limit, not a number, so
            # comparing against it blows up (it never showed up in a 1-month test).
            if len(results) < MEASUREMENTS_PAGE_LIMIT:
                break
            page += 1
            time.sleep(RATE_LIMIT_SLEEP_S)  # between pages of the same year

        time.sleep(RATE_LIMIT_SLEEP_S)  # between one year-chunk and the next

    return measurements, complete


def _pm25_sensor_ids(location: dict) -> list[int]:
    return [
        s["id"]
        for s in location.get("sensors", [])
        if s.get("parameter", {}).get("id") == PM25_PARAMETER_ID
    ]


def _load_existing(out_file: Path) -> dict | None:
    """Return the previous run's saved result for this station, if any."""
    if not out_file.exists():
        return None
    try:
        return json.loads(out_file.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def download_city(
    session: requests.Session,
    city: str,
    lat: float,
    lon: float,
    date_from: str,
    date_to: str,
    overwrite: bool = False,
) -> None:
    """Download every nearby station's PM2.5 series for one city into data/raw/openaq/<city>/.

    Each station's output file is {"complete": bool, "measurements": [...]}. If a file already
    exists with complete=True and overwrite=False, that station is skipped — this is what makes
    rerunning the whole script after a network drop cheap: only incomplete/missing stations are
    re-fetched.
    """
    out_dir = RAW_DIR / city
    out_dir.mkdir(parents=True, exist_ok=True)

    locations = fetch_locations(session, lat, lon)
    if not locations:
        log.warning("skipping %s — no stations returned", city)
        return

    (out_dir / "_locations.json").write_text(json.dumps(locations, indent=2))

    for loc in locations:
        location_id = loc["id"]
        sensor_ids = _pm25_sensor_ids(loc)
        if not sensor_ids:
            continue

        out_file = out_dir / f"{location_id}.json"
        existing = _load_existing(out_file)
        if existing and existing.get("complete") and not overwrite:
            log.info(
                "%s: location %s already complete (%d measurements) — skipping",
                city, location_id, len(existing.get("measurements", [])),
            )
            continue

        time.sleep(RATE_LIMIT_SLEEP_S)  # before starting the next station's requests
        measurements, complete = fetch_measurements(session, sensor_ids[0], date_from, date_to)
        out_file.write_text(json.dumps({"complete": complete, "measurements": measurements}))
        status = "complete" if complete else "INCOMPLETE — rerun to retry"
        log.info(
            "%s: location %s — %d measurements, %s -> %s",
            city, location_id, len(measurements), status, out_file,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Download OpenAQ PM2.5 data per city.")
    parser.add_argument("--city", choices=sorted(CITIES), help="Download just this one city.")
    parser.add_argument("--from", dest="date_from", default="2015-01-01")
    parser.add_argument("--to", dest="date_to", default=date.today().isoformat())
    parser.add_argument(
        "--overwrite", action="store_true", help="Re-download even stations already complete."
    )
    args = parser.parse_args()

    session = get_session()
    cities = {args.city: CITIES[args.city]} if args.city else CITIES
    remaining = list(cities)

    for city, (lat, lon) in cities.items():
        remaining.pop(0)
        log.info("downloading %s (%s, %s)", city, lat, lon)
        try:
            download_city(session, city, lat, lon, args.date_from, args.date_to, args.overwrite)
        except ApiKeyRejected as exc:
            # Fatal: stop the whole run instead of burning retries/requests against a dead key on
            # every remaining city (see ApiKeyRejected's docstring for why this happened before).
            skipped = ", ".join(remaining) if remaining else "none"
            log.error("%s — aborting run, not attempted: %s", exc, skipped)
            raise SystemExit(1) from exc
        time.sleep(RATE_LIMIT_SLEEP_S)


if __name__ == "__main__":
    main()
