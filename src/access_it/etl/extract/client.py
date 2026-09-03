import httpx
import time


BASE_URL = "https://competitions.ffc.fr"
USER_AGENT = "Mozilla/5.0"
HEADERS = {
    "User-Agent": USER_AGENT
}
REQUEST_TIMEOUT = 30.0


def make_client() -> httpx.Client:
    return httpx.Client(
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def get(client: httpx.Client, url: str, tries: int = 3, pause: int | float = 1) -> httpx.Response | None:
    pause = float(pause)
    for k in range(1, tries + 1):
        try:
            r = client.get(url)
        except httpx.RequestError:
            if k == tries:
                raise
            time.sleep(pause * k)
            continue

        if r.status_code == 404:
            return r
        if r.status_code >= 500 or r.status_code == 429:
            if k == tries:
                r.raise_for_status()
            time.sleep(pause * k)
            continue

        r.raise_for_status()
        return r
    return None
