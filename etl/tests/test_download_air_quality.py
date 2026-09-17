"""Unit tests for the OpenAQ download client (download.py).

These don't hit the real API — requests.Session.get is monkeypatched so the tests run offline
and in CI without needing a real OPENAQ_API_KEY. time.sleep is also monkeypatched to a no-op
(autouse fixture below) so retry-backoff tests don't actually wait tens of seconds.
"""

import json
from unittest.mock import MagicMock

import pytest
import requests

import download_air_quality as download


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(download.time, "sleep", lambda _seconds: None)


def _mock_response(json_body: dict, status_ok: bool = True) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_body
    if status_ok:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
    return resp


def test_fetch_locations_returns_results(monkeypatch):
    session = requests.Session()
    page = _mock_response({"results": [{"id": 1, "sensors": []}], "meta": {"found": 1}})
    monkeypatch.setattr(session, "get", MagicMock(return_value=page))

    locations = download.fetch_locations(session, 31.55, 74.34)

    assert locations == [{"id": 1, "sensors": []}]


def test_fetch_locations_handles_network_failure(monkeypatch):
    """Every attempt fails -> retries exhaust -> [] rather than raising."""
    session = requests.Session()
    monkeypatch.setattr(
        session, "get", MagicMock(side_effect=requests.exceptions.ConnectionError("no network"))
    )

    locations = download.fetch_locations(session, 31.55, 74.34)

    assert locations == []
    assert session.get.call_count == download.RETRY_ATTEMPTS


def test_fetch_locations_retries_then_succeeds(monkeypatch):
    """A transient failure followed by a good response should still return data."""
    session = requests.Session()
    good_page = _mock_response({"results": [{"id": 1, "sensors": []}], "meta": {"found": 1}})
    monkeypatch.setattr(
        session,
        "get",
        MagicMock(side_effect=[requests.exceptions.ConnectionError("blip"), good_page]),
    )

    locations = download.fetch_locations(session, 31.55, 74.34)

    assert locations == [{"id": 1, "sensors": []}]


def test_fetch_locations_handles_missing_city(monkeypatch):
    """A coordinate with no nearby stations should return [] instead of raising."""
    session = requests.Session()
    empty_page = _mock_response({"results": [], "meta": {"found": 0}})
    monkeypatch.setattr(session, "get", MagicMock(return_value=empty_page))

    locations = download.fetch_locations(session, 0.0, 0.0)

    assert locations == []


def test_fetch_locations_handles_http_error(monkeypatch):
    session = requests.Session()
    bad_response = _mock_response({}, status_ok=False)
    monkeypatch.setattr(session, "get", MagicMock(return_value=bad_response))

    locations = download.fetch_locations(session, 31.55, 74.34)

    assert locations == []


def test_fetch_locations_filters_to_reference_monitors(monkeypatch):
    session = requests.Session()
    results = [
        {"id": 1, "isMonitor": True, "provider": {"name": "StateAir"}},
        {"id": 2, "isMonitor": False, "provider": {"name": "AirGradient"}},
        {"id": 3, "isMonitor": False, "provider": {"name": "Hawanama"}},
    ]
    page = _mock_response({"results": results, "meta": {"found": 3}})
    monkeypatch.setattr(session, "get", MagicMock(return_value=page))

    locations = download.fetch_locations(session, 31.55, 74.34)

    assert [loc["id"] for loc in locations] == [1]


def test_fetch_locations_falls_back_when_no_reference_monitor(monkeypatch):
    """If a city has only low-cost sensors nearby, don't return an empty list — use them."""
    session = requests.Session()
    results = [{"id": 2, "isMonitor": False, "provider": {"name": "AirGradient"}}]
    page = _mock_response({"results": results, "meta": {"found": 1}})
    monkeypatch.setattr(session, "get", MagicMock(return_value=page))

    locations = download.fetch_locations(session, 31.55, 74.34)

    assert [loc["id"] for loc in locations] == [2]


def test_fetch_measurements_handles_non_numeric_found(monkeypatch):
    """Regression test: OpenAQ returns meta.found as the string ">1000" once the true
    count exceeds the page limit, instead of a number. A full-then-partial page pair
    must not crash when that happens (it did, in production, on a multi-year range).
    Only the 2015 chunk has data here; every other year in the range returns empty
    immediately, since fetch_measurements now requests one calendar year at a time.
    """
    session = requests.Session()

    def fake_get(url, params=None, timeout=None):
        if params["datetime_from"].startswith("2015"):
            if params["page"] == 1:
                return _mock_response(
                    {"results": [{"id": i} for i in range(1000)], "meta": {"found": ">1000"}}
                )
            return _mock_response({"results": [{"id": 1000}], "meta": {"found": ">1000"}})
        return _mock_response({"results": [], "meta": {"found": 0}})

    monkeypatch.setattr(session, "get", MagicMock(side_effect=fake_get))

    measurements, complete = download.fetch_measurements(
        session, 25135, "2015-01-01", "2026-09-15"
    )

    assert len(measurements) == 1001
    assert complete is True


def test_fetch_measurements_reports_incomplete_on_persistent_failure(monkeypatch):
    """If one year's requests never succeed, the station is marked incomplete (not silently
    treated as done) — this is what makes the file's "complete" flag trustworthy for resuming.
    """
    session = requests.Session()

    def fake_get(url, params=None, timeout=None):
        if params["datetime_from"].startswith("2016"):
            raise requests.exceptions.ConnectionError("down for this year")
        return _mock_response({"results": [{"id": 1}], "meta": {"found": 1}})

    monkeypatch.setattr(session, "get", MagicMock(side_effect=fake_get))

    measurements, complete = download.fetch_measurements(
        session, 25135, "2015-01-01", "2017-12-31"
    )

    assert complete is False
    # 2015 and 2017 still contributed their data even though 2016 failed entirely.
    assert len(measurements) == 2


def test_year_chunks_splits_on_calendar_year_boundaries():
    chunks = download._year_chunks("2015-06-01", "2017-03-01")

    assert chunks == [
        ("2015-06-01", "2015-12-31"),
        ("2016-01-01", "2016-12-31"),
        ("2017-01-01", "2017-03-01"),
    ]


def test_download_city_skips_already_complete_station(tmp_path, monkeypatch):
    monkeypatch.setattr(download, "RAW_DIR", tmp_path)
    out_dir = tmp_path / "lahore"
    out_dir.mkdir()
    (out_dir / "8664.json").write_text(
        json.dumps({"complete": True, "measurements": [{"id": 1}]})
    )

    session = requests.Session()
    location = {
        "id": 8664,
        "isMonitor": True,
        "sensors": [{"id": 25135, "parameter": {"id": download.PM25_PARAMETER_ID}}],
    }
    monkeypatch.setattr(
        download,
        "fetch_locations",
        lambda *a, **k: [location],
    )
    get_mock = MagicMock()
    monkeypatch.setattr(session, "get", get_mock)

    download.download_city(session, "lahore", 31.55, 74.34, "2015-01-01", "2020-01-01")

    get_mock.assert_not_called()


def test_pm25_sensor_ids_filters_to_pm25_only():
    location = {
        "sensors": [
            {"id": 10, "parameter": {"id": download.PM25_PARAMETER_ID}},
            {"id": 11, "parameter": {"id": 999}},
        ]
    }

    assert download._pm25_sensor_ids(location) == [10]
