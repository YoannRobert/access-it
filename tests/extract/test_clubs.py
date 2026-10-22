"""Unit tests of the FFC API calls of the extract step (no network)."""

import httpx
import pandas as pd
import pytest

from access_it.etl.extract import client as client_module
from access_it.etl.extract.client import RequestThrottle, get_required
from access_it.etl.extract.clubs import get_committees, get_region_bloc_data

DEPARTEMENTS = pd.DataFrame({
    "departement_code": ["44", "49"],
    "departement_name": ["Loire-Atlantique", "Maine-et-Loire"],
})


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    """Default throttle without delays (and without reading the settings)."""
    throttle = RequestThrottle({}, default_min_delay=0.0, sleep=lambda seconds: None)
    monkeypatch.setattr(client_module, "_default_throttle", throttle)


class JsonClient:
    """Client answering each URL with the JSON (or status code) of the first matching key."""

    def __init__(self, answers: dict):
        self.answers = answers

    def get(self, url: str) -> httpx.Response:
        request = httpx.Request("GET", url)
        for key, answer in self.answers.items():
            if key in url:
                if isinstance(answer, int):
                    return httpx.Response(answer, request=request)
                return httpx.Response(200, json=answer, request=request)
        return httpx.Response(404, request=request)


def region_block(committees: list[str]) -> dict:
    return {
        "region": "PAYS DE LA LOIRE",
        "extra_data": {"id_api": "52"},
        "committees": [{"post_title": name} for name in committees],
    }


def test_get_required_returns_the_response():
    response = get_required(JsonClient({"region": [{"label": "A"}]}), "https://velo.ffc.fr/region")
    assert response.json() == [{"label": "A"}]


@pytest.mark.parametrize("status_code", [404, 403])
def test_get_required_stops_the_extract_on_an_error_response(status_code):
    with pytest.raises(RuntimeError, match="Required request failed"):
        get_required(JsonClient({"region": status_code}), "https://velo.ffc.fr/region")


def test_region_block_gives_the_committees():
    reg, dep = get_region_bloc_data(region_block(["CD LOIRE-ATLANTIQUE"]), DEPARTEMENTS)
    assert reg == [{"regional_committee_id": "52", "name": "PAYS DE LA LOIRE"}]
    assert dep == [{
        "departemental_committee_id": "5244", "name": "CD LOIRE-ATLANTIQUE",
        "regional_committee_id": "52", "departement_code": "44",
    }]


def test_region_block_with_missing_keys_is_skipped_with_a_warning(caplog):
    block = region_block(["CD LOIRE-ATLANTIQUE"])
    del block["committees"]
    assert get_region_bloc_data(block, DEPARTEMENTS) == ([], [])
    assert "missing keys ['committees']" in caplog.text
    assert caplog.records[-1].levelname == "WARNING"


def test_region_block_leaves_the_departements_unchanged():
    departements = DEPARTEMENTS.copy()
    get_region_bloc_data(region_block(["CD MAINE-ET-LOIRE"]), departements)
    pd.testing.assert_frame_equal(departements, DEPARTEMENTS)


def test_get_committees_warns_about_a_skipped_region(monkeypatch, caplog):
    monkeypatch.setattr(
        "access_it.etl.extract.clubs.get_departement_mapping", lambda client: DEPARTEMENTS
    )
    client = JsonClient({
        "terms/region": [{"label": "Pays de la Loire", "value": "pdl"},
                         {"label": "Broken", "value": "broken"}],
        "comite?region=pdl": region_block(["CD LOIRE-ATLANTIQUE", "CD MAINE-ET-LOIRE"]),
        "comite?region=broken": {"overseas": [{"region": "X"}], "extra": 1},
    })
    reg, dep = get_committees(client)
    assert set(dep["departemental_committee_id"]) >= {"5244", "5249"}
    assert "52" in set(reg["regional_committee_id"])
    assert "missing keys" in caplog.text
    assert caplog.records[-1].levelname == "WARNING"
