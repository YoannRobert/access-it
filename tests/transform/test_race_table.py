"""Unit tests of the race table."""

from access_it.etl.transform import races


def test_women_only_organizations_are_skipped(tmp_path, monkeypatch):
    season, code = next(iter(races.WOMEN_ONLY_ORGANIZATIONS))
    season_dir = tmp_path / f"{season:4d}"
    season_dir.mkdir()
    (season_dir / f"{code}.html").write_text("<html></html>")

    def fail(*args, **kwargs):
        raise AssertionError("the page should not be read")

    monkeypatch.setattr(races, "read_results_html_file", fail)
    assert races.get_results_data(tmp_path) == []
