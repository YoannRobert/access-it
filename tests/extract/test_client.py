"""Unit tests of the HTTP client of the extract step (no network, simulated clock)."""

import httpx
import pytest

from access_it.etl.extract.client import (
    MAX_MIN_DELAY, RequestFailures, RequestThrottle, get, try_get
)

FFC = "https://competitions.ffc.fr/resultats/"
API = "https://velo.ffc.fr/wp-json/sn/terms/region"


class FakeClock:
    """Clock advanced by the simulated sleeps (and by `advance`), recording each sleep."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 6))
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeClient:
    """Client returning the given status codes (and headers), one per request."""

    def __init__(self, *responses: int | tuple[int, dict]):
        self.responses = list(responses)
        self.urls: list[str] = []

    def get(self, url: str) -> httpx.Response:
        self.urls.append(url)
        response = self.responses.pop(0)
        status_code, headers = response if isinstance(response, tuple) else (response, {})
        return httpx.Response(status_code, headers=headers, request=httpx.Request("GET", url))


def make_throttle(clock: FakeClock, jitter: float = 0.0) -> RequestThrottle:
    return RequestThrottle(
        {"competitions.ffc.fr": 0.3, "velo.ffc.fr": 1.0},
        default_min_delay=1.0,
        jitter=jitter,
        clock=clock,
        sleep=clock.sleep,
        random_fraction=lambda: 1.0,
    )


def test_first_request_does_not_wait():
    clock = FakeClock()
    get(FakeClient(200), FFC, throttle=make_throttle(clock))
    assert clock.sleeps == []


def test_requests_to_a_same_host_are_spaced_by_its_delay():
    clock = FakeClock()
    throttle = make_throttle(clock)
    client = FakeClient(200, 200, 200)
    get(client, FFC, throttle=throttle)
    get(client, FFC, throttle=throttle)
    clock.advance(0.1)
    get(client, FFC, throttle=throttle)
    assert clock.sleeps == [0.3, 0.2]  # only the remaining time is waited


def test_no_wait_when_the_delay_has_already_elapsed():
    clock = FakeClock()
    throttle = make_throttle(clock)
    client = FakeClient(200, 200)
    get(client, FFC, throttle=throttle)
    clock.advance(5)
    get(client, FFC, throttle=throttle)
    assert clock.sleeps == []


def test_different_hosts_do_not_wait_for_each_other():
    clock = FakeClock()
    throttle = make_throttle(clock)
    client = FakeClient(200, 200, 200)
    get(client, FFC, throttle=throttle)
    get(client, API, throttle=throttle)
    get(client, "https://example.org/page", throttle=throttle)
    assert clock.sleeps == []


def test_jitter_increases_the_delay():
    clock = FakeClock()
    throttle = make_throttle(clock, jitter=0.2)
    client = FakeClient(200, 200)
    get(client, API, throttle=throttle)
    get(client, API, throttle=throttle)
    assert clock.sleeps == [1.2]


def test_rejection_doubles_the_delay_of_the_host(capsys):
    clock = FakeClock()
    throttle = make_throttle(clock)
    response = get(FakeClient(429, 200), FFC, pause=0, throttle=throttle)
    assert response.status_code == 200
    assert throttle.min_delay("competitions.ffc.fr") == 0.6
    assert throttle.min_delay("velo.ffc.fr") == 1.0
    assert "delay between requests increased to 0.6 s" in capsys.readouterr().out


def test_delay_is_bounded_after_many_rejections():
    clock = FakeClock()
    throttle = make_throttle(clock)
    for _ in range(10):
        throttle.slow_down(FFC, 429)
    assert throttle.min_delay("competitions.ffc.fr") == MAX_MIN_DELAY


def test_retry_after_header_is_respected():
    clock = FakeClock()
    throttle = make_throttle(clock)
    client = FakeClient((429, {"Retry-After": "7"}), 200)
    assert get(client, FFC, throttle=throttle).status_code == 200
    assert clock.sleeps[0] == 7


def test_403_slows_down_and_raises():
    clock = FakeClock()
    throttle = make_throttle(clock)
    with pytest.raises(httpx.HTTPStatusError):
        get(FakeClient(403), FFC, throttle=throttle)
    assert throttle.min_delay("competitions.ffc.fr") == 0.6


def test_404_is_returned():
    clock = FakeClock()
    assert get(FakeClient(404), FFC, throttle=make_throttle(clock)).status_code == 404


# ---------------------------------------------------------------- try_get and RequestFailures

class ClientRaising:
    def get(self, url: str) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=httpx.Request("GET", url))


def test_try_get_returns_the_response():
    failures = RequestFailures()
    response = try_get(FakeClient(200), FFC, throttle=make_throttle(FakeClock()), failures=failures)
    assert response.status_code == 200
    assert failures.summary() == "All requests succeeded."


def test_try_get_records_an_http_error_instead_of_raising(capsys):
    failures = RequestFailures()
    response = try_get(FakeClient(403), FFC, throttle=make_throttle(FakeClock()), failures=failures)
    assert response is None
    assert "request failed (HTTP 403)" in capsys.readouterr().out
    summary = failures.summary()
    assert "1 request(s) failed" in summary
    assert "competitions.ffc.fr: HTTP 403 x 1" in summary


def test_try_get_records_a_network_error_after_all_retries():
    failures = RequestFailures()
    throttle = make_throttle(FakeClock())
    assert try_get(ClientRaising(), API, throttle=throttle, failures=failures) is None
    assert "velo.ffc.fr: ConnectTimeout x 1" in failures.summary()


def test_try_get_returns_a_404():
    failures = RequestFailures()
    response = try_get(FakeClient(404), FFC, throttle=make_throttle(FakeClock()), failures=failures)
    assert response.status_code == 404
    assert failures.failures == []
