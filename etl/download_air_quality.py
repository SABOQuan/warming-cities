"""Phase 1 — raw air-quality acquisition from OpenAQ v3 (PM2.5).

OpenAQ v3 has no "city" endpoint. A `location` is one physical monitoring station, so for each
city we do a radius search around its coordinates, keep the reference-grade monitors, and then
pull each station's PM2.5 sensor history.

What we pull, and why: MONTHLY aggregates (`/sensors/{id}/days/monthly`), not raw measurements.
The first version of this script pulled every raw hourly reading — one year per request, 1,000
readings per page — which is ~9 requests per station-year, >10,000 requests for 10 cities, and
the sustained volume got the API key suspended. Phase 2 only needs annual means, which we build
from monthly values, and the monthly endpoint returns each month's mean plus a `coverage` block
(observed vs. expected days) that Phase 2 uses to drop thin months. A station's whole history
fits in one page, so a full 10-city run costs a few hundred requests instead of tens of thousands.

Rate limiting — the part that must not go wrong again:

OpenAQ's free tier allows 60 requests/minute AND 2,000 requests/hour per key, and repeated
breaches lead to a temporary or permanent ban. Every HTTP request in this module goes through a
single RateLimiter (see below) that:

  * spaces requests at least MIN_INTERVAL_S apart,
  * enforces our OWN budgets at half of OpenAQ's limits (30/min, 1,000/hour) over sliding windows,
  * persists request timestamps to disk, so rerunning the script back-to-back still respects the
    hourly budget (an in-memory counter would reset on every rerun),
  * pauses until the window resets if OpenAQ's `x-ratelimit-remaining` header gets low,
  * counts retries as requests — retries go through the limiter like everything else.

And on the response side:

  * 429 means our accounting is wrong somewhere. We wait out the window once; a second 429 in the
    same run aborts the run rather than risk the "repeated breaches" that trigger a ban.
  * 401/403 mean the key is invalid or suspended — fatal, never retried.
  * A per-run hard cap (--max-requests, default 900) stops the script outright before it could
    approach the hourly limit even if every other safeguard failed.

Resumability: each sensor's output file records whether its download completed, so rerunning the
same command skips finished sensors and only retries what failed or is missing.

Usage:
    python download_air_quality.py --city lahore   # one city first, to check the key works
    python download_air_quality.py                 # all 11 cities, safe to rerun / resumes
    python download_air_quality.py --from 2016-01-01 --to 2025-12-31
    python download_air_quality.py --overwrite      # ignore existing files, re-download
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from collections import deque
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

from cities import CITIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BASE_URL = "https://api.openaq.org/v3"
PM25_PARAMETER_ID = 2  # OpenAQ's fixed id for PM2.5 — see /v3/parameters
RADIUS_M = 25_000  # meters; 25km is the max radius v3 accepts per request
PAGE_LIMIT = 1000  # rows per page; a sensor's monthly history (≤ ~200 months) fits in one
REQUEST_TIMEOUT_S = 30
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE_S = 10  # sleeps 10s, 20s between the 3 attempts

# Our own budgets: half of OpenAQ's published 60/min and 2,000/hour.
MAX_PER_MINUTE = 30
MAX_PER_HOUR = 1000
MIN_INTERVAL_S = 2.5  # ≤ 24 req/min even when the windows are empty
LOW_REMAINING_THRESHOLD = 5  # pause if OpenAQ says fewer than this many are left in its window
DEFAULT_MAX_REQUESTS_PER_RUN = 900

RAW_DIR = Path(__file__).parent / "data" / "raw" / "openaq"
REQUEST_LOG = RAW_DIR / "_request_log.json"


class ApiKeyRejected(RuntimeError):
    """OpenAQ returned 401/403 — the key is missing, invalid or suspended. Retrying, or moving on
    to the next city, would only send more requests to a dead key, so this stops the whole run."""


class RateLimitAbort(RuntimeError):
    """Raised to stop the run before we risk a ban: a repeated 429, or the per-run request cap."""


class RateLimiter:
    """Blocks before each request until sending it keeps us inside every budget.

    Timestamps of past requests are kept in a sliding window and saved to `log_path`, so the
    hourly budget holds across separate runs of the script, not just within one.
    """

    def __init__(
        self,
        log_path: Path | None = REQUEST_LOG,
        per_minute: int = MAX_PER_MINUTE,
        per_hour: int = MAX_PER_HOUR,
        min_interval: float = MIN_INTERVAL_S,
        max_requests: int = DEFAULT_MAX_REQUESTS_PER_RUN,
        clock=time.time,
        sleep=time.sleep,
    ) -> None:
        self.log_path = log_path
        self.per_minute = per_minute
        self.per_hour = per_hour
        self.min_interval = min_interval
        self.max_requests = max_requests
        self.clock = clock
        self.sleep = sleep
        self.sent_this_run = 0
        self.rate_limited_count = 0
        self.history: deque[float] = deque(self._load_history())

    def _load_history(self) -> list[float]:
        if self.log_path is None or not self.log_path.exists():
            return []
        try:
            stamps = json.loads(self.log_path.read_text())
        except (json.JSONDecodeError, OSError):
            return []
        cutoff = self.clock() - 3600
        return sorted(t for t in stamps if t > cutoff)

    def _save_history(self) -> None:
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(json.dumps(list(self.history)))

    def _prune(self, now: float) -> None:
        while self.history and self.history[0] <= now - 3600:
            self.history.popleft()

    def wait(self) -> None:
        """Sleep until one more request fits every budget, then record it as sent."""
        if self.sent_this_run >= self.max_requests:
            raise RateLimitAbort(
                f"reached the per-run cap of {self.max_requests} requests — stopping. Rerun "
                "later; finished sensors are skipped automatically."
            )
        while True:
            now = self.clock()
            self._prune(now)
            waits = [0.0]
            if self.history:
                waits.append(self.history[-1] + self.min_interval - now)
            last_minute = [t for t in self.history if t > now - 60]
            if len(last_minute) >= self.per_minute:
                waits.append(last_minute[-self.per_minute] + 60 - now)
            if len(self.history) >= self.per_hour:
                waits.append(self.history[-self.per_hour] + 3600 - now)
            delay = max(waits)
            if delay <= 0:
                break
            if delay > 60:
                log.info("hourly budget reached — pausing %.0f min", delay / 60)
            self.sleep(delay)

        self.history.append(self.clock())
        self.sent_this_run += 1
        self._save_history()

    def observe(self, resp: requests.Response) -> None:
        """Honour OpenAQ's own counters: if its window is nearly spent, wait for the reset."""
        remaining = resp.headers.get("x-ratelimit-remaining")
        if remaining is None or not remaining.isdigit():
            return
        if int(remaining) < LOW_REMAINING_THRESHOLD:
            pause = _reset_seconds(resp, default=60)
            log.warning("OpenAQ reports only %s requests left — pausing %ds", remaining, pause)
            self.sleep(pause)

    def on_rate_limited(self, resp: requests.Response) -> None:
        """First 429 in a run: wait out the window. Second: abort (repeated breaches = ban)."""
        self.rate_limited_count += 1
        if self.rate_limited_count > 1:
            raise RateLimitAbort(
                "OpenAQ returned 429 twice in one run — stopping to protect the API key. Wait "
                "at least an hour before rerunning."
            )
        pause = max(_reset_seconds(resp, default=60), 60) + 5
        log.warning("429 from OpenAQ — pausing %ds before continuing", pause)
        self.sleep(pause)


def _reset_seconds(resp: requests.Response, default: int) -> int:
    for header in ("Retry-After", "x-ratelimit-reset"):
        value = resp.headers.get(header)
        if value and value.isdigit():
            seconds = int(value)
            # The docs call x-ratelimit-reset a timestamp but show seconds; handle both.
            if seconds > 10**9:
                seconds = int(seconds - time.time())
            return max(seconds, 1)
    return default


def get_session() -> requests.Session:
    """Build a requests session carrying the OpenAQ API key from etl/.env."""
    load_dotenv()
    api_key = os.environ.get("OPENAQ_API_KEY")
    if not api_key or api_key == "your-api-key-here":
        raise RuntimeError(
            "OPENAQ_API_KEY is not set. Copy etl/.env.example to etl/.env and fill it in "
            "(sign up free at https://explore.openaq.org)."
        )
    session = requests.Session()
    session.headers.update({"X-API-Key": api_key})
    return session


def _request_json(
    session: requests.Session, limiter: RateLimiter, url: str, params: dict, what: str
) -> dict | None:
    """GET url through the rate limiter, retrying transient failures with backoff.

    Returns the parsed JSON, or None if every attempt failed (network down, persistent 5xx/408)
    — callers decide whether that means "skip this sensor". 401/403 raise ApiKeyRejected and a
    repeated 429 raises RateLimitAbort; neither is ever retried blindly.
    """
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        limiter.wait()
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
        except requests.exceptions.RequestException as exc:
            failure = str(exc)
        else:
            if resp.status_code in (401, 403):
                raise ApiKeyRejected(
                    f"OpenAQ rejected the API key ({resp.status_code}) on {what}. It is missing, "
                    "invalid, or suspended — check etl/.env and your OpenAQ account."
                )
            if resp.status_code == 429:
                limiter.on_rate_limited(resp)
                continue
            limiter.observe(resp)
            if resp.ok:
                return resp.json()
            failure = f"HTTP {resp.status_code}"
            if 400 <= resp.status_code < 500 and resp.status_code != 408:
                log.warning("%s failed: %s — not retrying a client error", what, failure)
                return None

        if attempt == RETRY_ATTEMPTS:
            log.warning("%s failed after %d attempts: %s", what, RETRY_ATTEMPTS, failure)
            return None
        backoff = RETRY_BACKOFF_BASE_S * (2 ** (attempt - 1))
        log.warning(
            "%s failed (attempt %d/%d): %s — retrying in %ds",
            what, attempt, RETRY_ATTEMPTS, failure, backoff,
        )
        limiter.sleep(backoff)
    return None


def _paginate(
    session: requests.Session, limiter: RateLimiter, url: str, params: dict, what: str
) -> tuple[list[dict], bool]:
    """Fetch every page of a list endpoint. Returns (results, complete)."""
    results: list[dict] = []
    page = 1
    while True:
        payload = _request_json(
            session, limiter, url, {**params, "limit": PAGE_LIMIT, "page": page},
            what=f"{what} page {page}",
        )
        if payload is None:
            return results, False
        batch = payload.get("results", [])
        results.extend(batch)
        # meta.found can be a string like ">1000", so a short page is the only safe stop signal.
        if len(batch) < PAGE_LIMIT:
            return results, True
        page += 1


def fetch_locations(
    session: requests.Session,
    limiter: RateLimiter,
    lat: float,
    lon: float,
    radius: int = RADIUS_M,
    monitors_only: bool = True,
) -> list[dict]:
    """Return PM2.5-capable stations within `radius` meters of (lat, lon).

    monitors_only=True keeps reference-grade government monitors (isMonitor) and drops low-cost
    community sensors; checked against Lahore, where 83 of 84 nearby stations were low-cost nodes
    with no data. If a city has no reference monitor at all, falls back to the low-cost sensors.
    Returns [] (rather than raising) on network failure or when nothing is nearby.
    """
    locations, _ = _paginate(
        session,
        limiter,
        f"{BASE_URL}/locations",
        {"coordinates": f"{lat},{lon}", "radius": radius, "parameters_id": PM25_PARAMETER_ID},
        what=f"locations near ({lat}, {lon})",
    )

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


def fetch_monthly(
    session: requests.Session, limiter: RateLimiter, sensor_id: int, date_from: str, date_to: str
) -> tuple[list[dict], bool]:
    """Monthly PM2.5 means (with coverage stats) for one sensor. Returns (months, complete)."""
    return _paginate(
        session,
        limiter,
        f"{BASE_URL}/sensors/{sensor_id}/days/monthly",
        {"date_from": date_from, "date_to": date_to},
        what=f"monthly PM2.5 for sensor {sensor_id}",
    )


def _pm25_sensor_ids(location: dict) -> list[int]:
    return [
        s["id"]
        for s in location.get("sensors", [])
        if s.get("parameter", {}).get("id") == PM25_PARAMETER_ID
    ]


def _overlaps(location: dict, date_from: str, date_to: str) -> bool:
    """False if the station's reported lifetime ends before, or starts after, our range — no
    point spending a request on a station that can't have data in the window."""
    first = (location.get("datetimeFirst") or {}).get("utc")
    last = (location.get("datetimeLast") or {}).get("utc")
    if last and last[:10] < date_from:
        return False
    if first and first[:10] > date_to:
        return False
    return True


def _load_existing(out_file: Path) -> dict | None:
    if not out_file.exists():
        return None
    try:
        return json.loads(out_file.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def download_city(
    session: requests.Session,
    limiter: RateLimiter,
    city: str,
    lat: float,
    lon: float,
    date_from: str,
    date_to: str,
    overwrite: bool = False,
) -> None:
    """Download monthly PM2.5 for every nearby station into data/raw/openaq/<city>/.

    Writes `_locations.json` (station metadata) plus one `<sensor_id>.json` per PM2.5 sensor:
    {"complete", "location_id", "sensor_id", "date_from", "date_to", "results"}.
    """
    out_dir = RAW_DIR / city
    out_dir.mkdir(parents=True, exist_ok=True)

    locations = fetch_locations(session, limiter, lat, lon)
    if not locations:
        log.warning("skipping %s — no stations returned", city)
        return
    (out_dir / "_locations.json").write_text(json.dumps(locations, indent=2))

    for loc in locations:
        if not _overlaps(loc, date_from, date_to):
            log.info("%s: location %s has no data in range — skipping", city, loc["id"])
            continue
        for sensor_id in _pm25_sensor_ids(loc):
            out_file = out_dir / f"{sensor_id}.json"
            existing = _load_existing(out_file)
            if existing and existing.get("complete") and not overwrite:
                log.info("%s: sensor %s already complete — skipping", city, sensor_id)
                continue

            months, complete = fetch_monthly(session, limiter, sensor_id, date_from, date_to)
            out_file.write_text(
                json.dumps(
                    {
                        "complete": complete,
                        "location_id": loc["id"],
                        "location_name": loc.get("name"),
                        "sensor_id": sensor_id,
                        "date_from": date_from,
                        "date_to": date_to,
                        "results": months,
                    },
                    indent=2,
                )
            )
            log.info(
                "%s: sensor %s (%s) — %d months, %s",
                city, sensor_id, loc.get("name"), len(months),
                "complete" if complete else "INCOMPLETE — rerun to retry",
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Download OpenAQ monthly PM2.5 per city.")
    parser.add_argument("--city", choices=sorted(CITIES), help="Download just this one city.")
    parser.add_argument("--from", dest="date_from", default="2013-01-01")
    parser.add_argument("--to", dest="date_to", default=date.today().isoformat())
    parser.add_argument(
        "--overwrite", action="store_true", help="Re-download sensors already complete."
    )
    parser.add_argument(
        "--max-requests", type=int, default=DEFAULT_MAX_REQUESTS_PER_RUN,
        help="Hard stop after this many requests in one run.",
    )
    args = parser.parse_args()

    session = get_session()
    limiter = RateLimiter(max_requests=args.max_requests)
    cities = {args.city: CITIES[args.city]} if args.city else CITIES
    remaining = list(cities)

    for city, (lat, lon) in cities.items():
        remaining.pop(0)
        log.info("downloading %s (%s, %s)", city, lat, lon)
        try:
            download_city(
                session, limiter, city, lat, lon, args.date_from, args.date_to, args.overwrite
            )
        except (ApiKeyRejected, RateLimitAbort) as exc:
            log.error("%s — aborting. Not attempted: %s", exc, ", ".join(remaining) or "none")
            raise SystemExit(1) from exc

    log.info("done — %d requests sent this run", limiter.sent_this_run)


if __name__ == "__main__":
    main()
