"""Unit tests for the OpenAQ download client (download_air_quality.py).

These don't hit the real API — requests.Session.get is monkeypatched so the tests run offline and
in CI without an OPENAQ_API_KEY. The rate limiter gets a fake clock whose sleep() just advances
time, so the tests both run instantly and can assert exactly how long the limiter would wait.
"""

import json
from unittest.mock import MagicMock

import pytest
import requests

import download_air_quality as download


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def limiter(clock):
    return download.RateLimiter(log_path=None, clock=clock.time, sleep=clock.sleep)


def _mock_response(json_body: dict, status: int = 200, headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.ok = 200 <= status < 300
    resp.headers = headers or {}
    resp.json.return_value = json_body
    return resp


# --- RateLimiter -------------------------------------------------------------------------------


def test_limiter_spaces_requests_by_min_interval(limiter, clock):
    start = clock.now
    for _ in range(5):
        limiter.wait()

    assert clock.now - start == pytest.approx(4 * download.MIN_INTERVAL_S)


def test_limiter_never_exceeds_per_minute_budget(clock):
    limiter = download.RateLimiter(
        log_path=None, min_interval=0, clock=clock.time, sleep=clock.sleep
    )
    stamps = []
    for _ in range(100):
        limiter.wait()
        stamps.append(clock.now)

    for i, t in enumerate(stamps):
        in_window = [s for s in stamps[: i + 1] if s > t - 60]
        assert len(in_window) <= download.MAX_PER_MINUTE


def test_limiter_never_exceeds_per_hour_budget(clock):
    limiter = download.RateLimiter(
        log_path=None, min_interval=0, per_minute=10_000, per_hour=50,
        clock=clock.time, sleep=clock.sleep,
    )
    stamps = []
    for _ in range(120):
        limiter.wait()
        stamps.append(clock.now)

    for i, t in enumerate(stamps):
        assert len([s for s in stamps[: i + 1] if s > t - 3600]) <= 50


def test_limiter_budget_survives_a_rerun(tmp_path, clock):
    """Requests from a previous run in the last hour still count — rerunning can't reset it."""
    log_path = tmp_path / "_request_log.json"
    first = download.RateLimiter(
        log_path=log_path, min_interval=0, per_minute=10_000, per_hour=5,
        clock=clock.time, sleep=clock.sleep,
    )
    for _ in range(5):
        first.wait()

    second = download.RateLimiter(
        log_path=log_path, min_interval=0, per_minute=10_000, per_hour=5,
        clock=clock.time, sleep=clock.sleep,
    )
    before = clock.now
    second.wait()

    assert clock.now - before >= 3599


def test_limiter_stops_at_per_run_cap(clock):
    limiter = download.RateLimiter(
        log_path=None, min_interval=0, max_requests=3, clock=clock.time, sleep=clock.sleep
    )
    for _ in range(3):
        limiter.wait()

    with pytest.raises(download.RateLimitAbort):
        limiter.wait()


def test_limiter_pauses_when_openaq_reports_low_remaining(limiter, clock):
    resp = _mock_response({}, headers={"x-ratelimit-remaining": "2", "x-ratelimit-reset": "40"})

    limiter.observe(resp)

    assert clock.slept == [40]


# --- _request_json -----------------------------------------------------------------------------


def test_401_is_fatal_and_not_retried(limiter, monkeypatch):
    session = requests.Session()
    monkeypatch.setattr(session, "get", MagicMock(return_value=_mock_response({}, status=401)))

    with pytest.raises(download.ApiKeyRejected):
        download._request_json(session, limiter, "url", {}, what="test")
    assert session.get.call_count == 1


def test_single_429_waits_then_retries(limiter, clock, monkeypatch):
    session = requests.Session()
    monkeypatch.setattr(
        session,
        "get",
        MagicMock(
            side_effect=[
                _mock_response({}, status=429, headers={"Retry-After": "30"}),
                _mock_response({"results": [1]}),
            ]
        ),
    )

    assert download._request_json(session, limiter, "url", {}, what="test") == {"results": [1]}
    assert max(clock.slept) >= 60  # waits at least a full minute window, not just Retry-After


def test_second_429_aborts_the_run(limiter, monkeypatch):
    session = requests.Session()
    monkeypatch.setattr(session, "get", MagicMock(return_value=_mock_response({}, status=429)))

    with pytest.raises(download.RateLimitAbort):
        download._request_json(session, limiter, "url", {}, what="test")
    assert session.get.call_count == 2


def test_network_failure_retries_then_gives_up(limiter, monkeypatch):
    session = requests.Session()
    monkeypatch.setattr(
        session, "get", MagicMock(side_effect=requests.exceptions.ConnectionError("down"))
    )

    assert download._request_json(session, limiter, "url", {}, what="test") is None
    assert session.get.call_count == download.RETRY_ATTEMPTS
    assert limiter.sent_this_run == download.RETRY_ATTEMPTS  # retries count against the budget


def test_404_is_not_retried(limiter, monkeypatch):
    session = requests.Session()
    monkeypatch.setattr(session, "get", MagicMock(return_value=_mock_response({}, status=404)))

    assert download._request_json(session, limiter, "url", {}, what="test") is None
    assert session.get.call_count == 1


# --- fetch_locations / fetch_monthly -----------------------------------------------------------


def test_fetch_locations_filters_to_reference_monitors(limiter, monkeypatch):
    session = requests.Session()
    results = [{"id": 1, "isMonitor": True}, {"id": 2, "isMonitor": False}]
    page = _mock_response({"results": results})
    monkeypatch.setattr(session, "get", MagicMock(return_value=page))

    assert [loc["id"] for loc in download.fetch_locations(session, limiter, 31.5, 74.3)] == [1]


def test_fetch_locations_falls_back_when_no_reference_monitor(limiter, monkeypatch):
    session = requests.Session()
    page = _mock_response({"results": [{"id": 2, "isMonitor": False}]})
    monkeypatch.setattr(session, "get", MagicMock(return_value=page))

    assert [loc["id"] for loc in download.fetch_locations(session, limiter, 31.5, 74.3)] == [2]


def test_fetch_locations_handles_missing_city(limiter, monkeypatch):
    session = requests.Session()
    monkeypatch.setattr(session, "get", MagicMock(return_value=_mock_response({"results": []})))

    assert download.fetch_locations(session, limiter, 0.0, 0.0) == []


def test_fetch_monthly_uses_monthly_endpoint_and_paginates(limiter, monkeypatch):
    session = requests.Session()
    full = _mock_response({"results": [{"value": 1}] * download.PAGE_LIMIT})
    tail = _mock_response({"results": [{"value": 2}]})
    monkeypatch.setattr(session, "get", MagicMock(side_effect=[full, tail]))

    months, complete = download.fetch_monthly(session, limiter, 42, "2015-01-01", "2025-01-01")

    assert len(months) == download.PAGE_LIMIT + 1
    assert complete is True
    url, = session.get.call_args.args
    assert url.endswith("/sensors/42/days/monthly")
    assert session.get.call_args.kwargs["params"]["date_from"] == "2015-01-01"


def test_fetch_monthly_reports_incomplete_on_failure(limiter, monkeypatch):
    session = requests.Session()
    monkeypatch.setattr(
        session, "get", MagicMock(side_effect=requests.exceptions.ConnectionError("down"))
    )

    months, complete = download.fetch_monthly(session, limiter, 42, "2015-01-01", "2025-01-01")

    assert (months, complete) == ([], False)


# --- download_city -----------------------------------------------------------------------------


def _location(**overrides):
    loc = {
        "id": 8664,
        "name": "US Consulate",
        "isMonitor": True,
        "sensors": [{"id": 25135, "parameter": {"id": download.PM25_PARAMETER_ID}}],
    }
    loc.update(overrides)
    return loc


def test_download_city_skips_already_complete_sensor(tmp_path, limiter, monkeypatch):
    monkeypatch.setattr(download, "RAW_DIR", tmp_path)
    (tmp_path / "lahore").mkdir()
    (tmp_path / "lahore" / "25135.json").write_text(json.dumps({"complete": True, "results": []}))
    monkeypatch.setattr(download, "fetch_locations", lambda *a, **k: [_location()])
    session = requests.Session()
    monkeypatch.setattr(session, "get", MagicMock())

    download.download_city(session, limiter, "lahore", 31.5, 74.3, "2015-01-01", "2020-01-01")

    session.get.assert_not_called()


def test_download_city_skips_stations_outside_date_range(tmp_path, limiter, monkeypatch):
    monkeypatch.setattr(download, "RAW_DIR", tmp_path)
    old = _location(datetimeLast={"utc": "2012-06-01T00:00:00Z"})
    monkeypatch.setattr(download, "fetch_locations", lambda *a, **k: [old])
    session = requests.Session()
    monkeypatch.setattr(session, "get", MagicMock())

    download.download_city(session, limiter, "lahore", 31.5, 74.3, "2015-01-01", "2020-01-01")

    session.get.assert_not_called()


def test_download_city_writes_sensor_file(tmp_path, limiter, monkeypatch):
    monkeypatch.setattr(download, "RAW_DIR", tmp_path)
    monkeypatch.setattr(download, "fetch_locations", lambda *a, **k: [_location()])
    session = requests.Session()
    month = {"value": 88.1, "period": {"datetimeFrom": {"utc": "2019-01-01T00:00:00Z"}}}
    page = _mock_response({"results": [month]})
    monkeypatch.setattr(session, "get", MagicMock(return_value=page))

    download.download_city(session, limiter, "lahore", 31.5, 74.3, "2015-01-01", "2020-01-01")

    saved = json.loads((tmp_path / "lahore" / "25135.json").read_text())
    assert saved["complete"] is True
    assert saved["location_id"] == 8664
    assert saved["results"] == [month]


def test_pm25_sensor_ids_filters_to_pm25_only():
    location = {
        "sensors": [
            {"id": 10, "parameter": {"id": download.PM25_PARAMETER_ID}},
            {"id": 11, "parameter": {"id": 999}},
        ]
    }

    assert download._pm25_sensor_ids(location) == [10]
