"""HTTP client of the extract step, with a minimal delay between requests to a same site."""

import random
import time

from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

BASE_URL = "https://competitions.ffc.fr"
USER_AGENT = "Mozilla/5.0"
HEADERS = {
    "User-Agent": USER_AGENT
}
REQUEST_TIMEOUT = 30.0

# Minimal delay (seconds) between two requests to a same host
MIN_DELAY_BY_HOST = {
    "competitions.ffc.fr": 0.3,
    "velo.ffc.fr": 1.0,
}
STARTLISTS_MIN_DELAY = 0.3  # host read from the STARTLISTS_URL setting
DEFAULT_MIN_DELAY = 1.0
DELAY_JITTER = 0.2  # each delay is randomly increased by up to 20%
MAX_MIN_DELAY = 10.0  # upper bound of the delay after slowdowns
SLOWDOWN_STATUS_CODES = {403, 429}  # the delay of the host doubles on these responses
MAX_LISTED_FAILURES = 5  # failed URLs listed in the summary of the run


class RequestThrottle:
    """Enforce a minimal delay between two requests to a same host.

    Only the remaining time since the last request to the host is waited.
    The delay of a host doubles (up to MAX_MIN_DELAY) when it rejects requests.
    """

    def __init__(
            self,
            min_delay_by_host: dict[str, float],
            default_min_delay: float = DEFAULT_MIN_DELAY,
            jitter: float = DELAY_JITTER,
            clock: Callable[[], float] = time.monotonic,
            sleep: Callable[[float], None] = time.sleep,
            random_fraction: Callable[[], float] = random.random,
    ):
        self.min_delay_by_host = dict(min_delay_by_host)
        self.default_min_delay = default_min_delay
        self.jitter = jitter
        self.clock = clock
        self.sleep = sleep
        self.random_fraction = random_fraction
        self.last_request_time: dict[str, float] = {}

    def min_delay(self, host: str) -> float:
        return self.min_delay_by_host.get(host, self.default_min_delay)

    def wait(self, url: str) -> None:
        """Wait, if needed, before a request to the host of `url`, then record its time."""
        host = urlsplit(url).hostname or ""
        if host in self.last_request_time:
            delay = self.min_delay(host) * (1 + self.jitter * self.random_fraction())
            remaining = delay - (self.clock() - self.last_request_time[host])
            if remaining > 0:
                self.sleep(remaining)
        self.last_request_time[host] = self.clock()

    def slow_down(self, url: str, status_code: int) -> None:
        """Double the delay of the host of `url` (up to MAX_MIN_DELAY)."""
        host = urlsplit(url).hostname or ""
        delay = min(2 * self.min_delay(host), MAX_MIN_DELAY)
        if delay > self.min_delay(host):
            print(f"Warning: HTTP {status_code} from {host}, delay between requests "
                  f"increased to {delay:.1f} s")
        self.min_delay_by_host[host] = delay


def make_throttle() -> RequestThrottle:
    """Throttle with the delays of this module, including the startlists host."""
    from access_it.config import get_settings

    min_delay_by_host = dict(MIN_DELAY_BY_HOST)
    startlists_host = urlsplit(get_settings().startlists_url).hostname
    if startlists_host:
        min_delay_by_host[startlists_host] = STARTLISTS_MIN_DELAY
    return RequestThrottle(min_delay_by_host)


_default_throttle: RequestThrottle | None = None


def default_throttle() -> RequestThrottle:
    """Throttle shared by all the requests of the process, created on first use."""
    global _default_throttle
    if _default_throttle is None:
        _default_throttle = make_throttle()
    return _default_throttle


def make_client() -> httpx.Client:
    return httpx.Client(
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def retry_after_seconds(response: httpx.Response) -> float | None:
    """Delay requested by the server in the Retry-After header (seconds only)."""
    value = response.headers.get("Retry-After", "").strip()
    return float(value) if value.isdigit() else None


def get(
        client: httpx.Client,
        url: str,
        tries: int = 3,
        pause: int | float = 1,
        throttle: RequestThrottle | None = None
    ) -> httpx.Response | None:
    """GET `url`, waiting the minimal delay of its host and retrying on transient errors.

    Network errors, 5xx and 429 responses are retried (`tries` attempts, waiting
    `pause` seconds times the attempt number, or the Retry-After delay of a 429).
    A 404 response is returned; other error responses raise httpx.HTTPStatusError.
    """
    throttle = throttle or default_throttle()
    pause = float(pause)
    for k in range(1, tries + 1):
        throttle.wait(url)
        try:
            r = client.get(url)
        except httpx.RequestError:
            if k == tries:
                raise
            throttle.sleep(pause * k)
            continue

        if r.status_code in SLOWDOWN_STATUS_CODES:
            throttle.slow_down(url, r.status_code)
        if r.status_code == 404:
            return r
        if r.status_code >= 500 or r.status_code == 429:
            if k == tries:
                r.raise_for_status()
            throttle.sleep(retry_after_seconds(r) or pause * k)
            continue

        r.raise_for_status()
        return r
    return None


class RequestFailures:
    """Requests that failed for good during the run (after all retries)."""

    def __init__(self):
        self.failures: list[tuple[str, str, str]] = []  # (host, reason, url)

    def record(self, url: str, error: httpx.HTTPError) -> str:
        """Record a failure and return its reason (e.g. 'HTTP 403', 'ConnectTimeout')."""
        if isinstance(error, httpx.HTTPStatusError):
            reason = f"HTTP {error.response.status_code}"
        else:
            reason = type(error).__name__
        self.failures.append((urlsplit(url).hostname or "", reason, url))
        return reason

    def summary(self) -> str:
        """Number of failed requests per host and reason, with a few URLs."""
        if not self.failures:
            return "All requests succeeded."
        counts: dict[tuple[str, str], int] = {}
        for host, reason, _ in self.failures:
            counts[(host, reason)] = counts.get((host, reason), 0) + 1
        lines = [f"Warning: {len(self.failures)} request(s) failed, retried at the next run:"]
        lines += [
            f"  {host}: {reason} x {count}" for (host, reason), count in sorted(counts.items())
        ]
        lines += [f"  e.g. {url}" for _, _, url in self.failures[:MAX_LISTED_FAILURES]]
        return "\n".join(lines)


FAILURES = RequestFailures()  # failures of the whole process, summarized by scripts/extract.py


def try_get(
        client: httpx.Client,
        url: str,
        throttle: RequestThrottle | None = None,
        failures: RequestFailures | None = None
    ) -> httpx.Response | None:
    """Like get(), but return None instead of raising when the request fails for good.

    The failure is recorded (in FAILURES by default) and printed: the caller
    skips the page without caching it, so that it is requested again at the
    next run. A 404 response is returned, as by get().
    """
    failures = failures if failures is not None else FAILURES
    try:
        return get(client, url, throttle=throttle)
    except httpx.HTTPError as error:
        reason = failures.record(url, error)
        print(f"Warning: request failed ({reason}): {url}")
        return None


def get_required(client: httpx.Client, url: str) -> httpx.Response:
    """GET a resource the extract step cannot do without (API, reference pages).

    Same delays and retries as get(), but any error response (404 included)
    or network error raises a RuntimeError naming the URL: the extract step
    stops, since the reference data (clubs, committees...) would be incomplete.
    """
    try:
        response = get(client, url)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise RuntimeError(
            f"Required request failed ({error}): {url}. The extract step is stopped, "
            f"since the reference data would be incomplete; run it again later."
        ) from error
    return response
