"""Phase 1 — raw data acquisition: temperature (NOAA GHCN-Monthly v4).

Unlike OpenAQ (download_air_quality.py), NOAA has no per-city or per-station API to query. They
publish the ENTIRE global network as one bulk archive — station data for 25,000+ stations
worldwide, all in two plain-text files inside one .tar.gz. So the approach here is different:

1. Download that one archive (a few dozen MB, a few dozen times smaller than air quality's 10
   separate per-station histories, and no rate limit / API key / ToS risk since it's a static
   file, not an API).
2. Parse the station inventory (.inv) to find, for each of our 11 cities, the single nearest
   weather station — same "nearest station" idea as the OpenAQ radius search, just done locally
   on the inventory file instead of via HTTP calls.
3. Parse the data file (.dat) and pull out only the rows for those 11 matched stations.

We use the "qcf" variant (quality-controlled AND bias-corrected via NOAA's Pairwise Homogeneity
Algorithm — station moves, instrument swaps, and time-of-observation changes are corrected for).
The raw "qcu" variant can show artificial jumps from those non-climate causes, which would distort
the warming-trend story this whole project is telling — see ROADMAP.md's Datasets table.

There's no separate "current temperature" fetch: GHCN-Monthly is monthly with a reporting lag (not
live/real-time), so the most recent row already present in a station's downloaded history *is* the
current figure for this project's purposes — nothing extra to do for that.

Usage:
    python download_temperature.py                # all 11 cities, safe to rerun/resumes
    python download_temperature.py --city lahore   # just one, for testing
    python download_temperature.py --overwrite     # re-download the archive, redo station matching
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import tarfile
from datetime import date
from pathlib import Path

import requests

from cities import CITIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# "qcf" = quality-controlled + bias-corrected (adjusted for station moves/instrument changes).
# See module docstring for why this variant over "qcu" (raw) or "qfe" (adjusted but capped to
# 1961-2010).
ARCHIVE_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/v4/ghcnm.tavg.latest.qcf.tar.gz"
REQUEST_TIMEOUT_S = 30
MISSING_VALUE = -9999  # GHCN's sentinel for "no reading this month"
MAX_STATION_DISTANCE_KM = 100  # sanity threshold — see find_best_station docstring
RECENT_YEARS_CUTOFF = 5  # a station's most recent reading must be within this many years to
# count as "reporting currently" — see find_best_station docstring

RAW_DIR = Path(__file__).parent / "data" / "raw" / "ghcn"
ARCHIVE_PATH = RAW_DIR / "ghcnm.tavg.latest.qcf.tar.gz"
EXTRACT_DIR = RAW_DIR / "extracted"


def download_archive(overwrite: bool = False) -> None:
    """Fetch the one global GHCN-Monthly archive, unless it's already on disk.

    No per-city pacing here (unlike OpenAQ) — this is a single plain HTTPS file download, not a
    rate-limited API, so there's nothing to throttle.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if ARCHIVE_PATH.exists() and not overwrite:
        log.info("archive already downloaded at %s — skipping (use --overwrite)", ARCHIVE_PATH)
        return

    log.info("downloading %s", ARCHIVE_URL)
    with requests.get(ARCHIVE_URL, stream=True, timeout=REQUEST_TIMEOUT_S) as resp:
        resp.raise_for_status()
        with ARCHIVE_PATH.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
    log.info("saved archive to %s", ARCHIVE_PATH)


def extract_archive(overwrite: bool = False) -> tuple[Path, Path]:
    """Unpack the archive and return (path to .dat file, path to .inv file).

    The archive contains one versioned subdirectory (e.g. ghcnm.v4.x.x.YYYYMMDD/) holding both
    files — found by globbing rather than hardcoding the version-stamped name, since that stamp
    changes with every NOAA release.
    """
    if not EXTRACT_DIR.exists() or overwrite:
        EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
        log.info("extracting %s", ARCHIVE_PATH)
        with tarfile.open(ARCHIVE_PATH, "r:gz") as tar:
            tar.extractall(EXTRACT_DIR, filter="data")

    dat_files = list(EXTRACT_DIR.glob("**/*.dat"))
    inv_files = list(EXTRACT_DIR.glob("**/*.inv"))
    if not dat_files or not inv_files:
        raise RuntimeError(
            f"expected a .dat and .inv file under {EXTRACT_DIR} after extraction — archive layout "
            "may have changed upstream."
        )
    return dat_files[0], inv_files[0]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two (lat, lon) points."""
    r = 6371.0  # earth radius, km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def parse_inventory(inv_path: Path) -> dict[str, dict]:
    """Parse the .inv file into {station_id: {lat, lon, elevation, name}}.

    Fixed-width columns per NOAA's readme.txt (1-indexed, inclusive):
    ID 1-11, LATITUDE 13-20, LONGITUDE 22-30, STNELEV 32-37, NAME 39-68.
    """
    stations: dict[str, dict] = {}
    with inv_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if len(line) < 68:
                continue  # skip blank/short trailing lines
            stations[line[0:11]] = {
                "lat": float(line[12:20]),
                "lon": float(line[21:30]),
                "elevation_m": float(line[31:37]),
                "name": line[38:68].strip(),
            }
    return stations


def scan_station_last_years(dat_path: Path) -> dict[str, int]:
    """One pass over the whole .dat file to find each station's most recent TAVG year.

    Needed because "nearest station" and "station that's actually still reporting" are often
    different stations — found by hand for London: the single nearest station (Hampstead, 6.9km)
    stopped reporting in 2011, while Heathrow, only 23km away, has an unbroken record to the
    present. Picking on distance alone would have silently produced a temperature series that
    goes dead 15 years before "now" for a city where a current one was available a few km further
    out. This scan lets find_best_station prefer currency over raw proximity.
    """
    last_year: dict[str, int] = {}
    with dat_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if line[15:19] != "TAVG":
                continue
            station_id = line[0:11]
            year = int(line[11:15])
            if year > last_year.get(station_id, 0):
                last_year[station_id] = year
    return last_year


def find_best_station(
    stations: dict[str, dict], last_year: dict[str, int], lat: float, lon: float
) -> tuple[str, float]:
    """Return (station_id, distance_km) of the best station to represent (lat, lon).

    "Best" means: prefer a station whose data reaches within RECENT_YEARS_CUTOFF of today (so the
    city's series has an actual "current" figure, not one that goes dead years ago) — among those,
    pick the nearest. If NO nearby station has recent data, fall back to the single nearest
    station overall and log a warning, rather than silently returning a stale series.

    MAX_STATION_DISTANCE_KM is a separate sanity check: past that distance, even a "best" match
    may not represent the city's local climate well.
    """
    recent_cutoff_year = date.today().year - RECENT_YEARS_CUTOFF

    def distance_to(sid: str) -> float:
        return _haversine_km(lat, lon, stations[sid]["lat"], stations[sid]["lon"])

    reporting_recently = [sid for sid in stations if last_year.get(sid, 0) >= recent_cutoff_year]
    candidates = reporting_recently or list(stations)
    if not reporting_recently:
        log.warning(
            "no station near (%s, %s) has TAVG data since %d — falling back to nearest station "
            "regardless of currency",
            lat, lon, recent_cutoff_year,
        )

    best_id = min(candidates, key=distance_to)
    distance = distance_to(best_id)
    if distance > MAX_STATION_DISTANCE_KM:
        log.warning(
            "best station to (%s, %s) is %.0fkm away (%s, %s) — may not represent local climate",
            lat, lon, distance, best_id, stations[best_id]["name"],
        )
    return best_id, distance


def parse_station_series(dat_path: Path, station_id: str) -> list[dict]:
    """Pull one station's monthly TAVG series out of the (huge, all-stations) .dat file.

    Fixed-width columns per NOAA's readme.txt (1-indexed, inclusive):
    ID 1-11, YEAR 12-15, ELEMENT 16-19, then 12 repeating 8-char month blocks starting at column
    20: 5-char VALUE (hundredths of a degree C, -9999 = missing) + 1-char DMFLAG + 1-char QCFLAG +
    1-char DSFLAG. We only keep VALUE here — the flags are NOAA's own QC provenance codes, not
    needed once we've already chosen the quality-controlled ("qcf") file variant.

    Streams the file line by line rather than loading it whole — it holds every station on earth,
    not just the ones we want.
    """
    readings = []
    with dat_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if line[0:11] != station_id or line[15:19] != "TAVG":
                continue
            year = int(line[11:15])
            for month in range(1, 13):
                offset = 19 + (month - 1) * 8
                raw_value = line[offset:offset + 5]
                try:
                    value = int(raw_value)
                except ValueError:
                    continue  # blank trailing month, e.g. a not-yet-reported current year
                if value == MISSING_VALUE:
                    continue
                readings.append({"year": year, "month": month, "temp_c": value / 100.0})
    return readings


def download_city(
    city: str,
    lat: float,
    lon: float,
    stations: dict[str, dict],
    last_year: dict[str, int],
    dat_path: Path,
    overwrite: bool = False,
) -> None:
    """Match one city to its best station (see find_best_station) and write that station's series
    to data/raw/ghcn/<city>.json — {"station_id", "station_name", "distance_km", "readings": [...]}.

    Resumable the same way download_air_quality.py is: an existing output file is trusted and
    skipped unless --overwrite is passed, since station matching + parsing the .dat file is the
    only "slow" part here (no network calls per city).
    """
    out_file = RAW_DIR / f"{city}.json"
    if out_file.exists() and not overwrite:
        log.info("%s: already have %s — skipping", city, out_file)
        return

    station_id, distance = find_best_station(stations, last_year, lat, lon)
    station = stations[station_id]
    readings = parse_station_series(dat_path, station_id)
    if not readings:
        log.warning("%s: station %s (%s) has no TAVG readings", city, station_id, station["name"])

    out_file.write_text(json.dumps({
        "station_id": station_id,
        "station_name": station["name"],
        "distance_km": round(distance, 1),
        "readings": readings,
    }, indent=2))
    log.info(
        "%s: station %s (%s), %.0fkm away — %d monthly readings -> %s",
        city, station_id, station["name"], distance, len(readings), out_file,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Download NOAA GHCN-Monthly temperature data.")
    parser.add_argument("--city", choices=sorted(CITIES), help="Process just this one city.")
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Re-download the archive and redo station matching, even if already done.",
    )
    args = parser.parse_args()

    download_archive(args.overwrite)
    dat_path, inv_path = extract_archive(args.overwrite)
    stations = parse_inventory(inv_path)
    log.info("loaded %d stations from inventory", len(stations))
    last_year = scan_station_last_years(dat_path)

    cities = {args.city: CITIES[args.city]} if args.city else CITIES
    for city, (lat, lon) in cities.items():
        download_city(city, lat, lon, stations, last_year, dat_path, args.overwrite)


if __name__ == "__main__":
    main()
