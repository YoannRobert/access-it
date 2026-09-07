import httpx
from access_it.common.text import normalize_string_and_fold_case


def get_regions(client: httpx.Client) -> list[dict[str, str]]:
    r = client.get("https://velo.ffc.fr/wp-json/sn/terms/region")
    r.raise_for_status()
    return r.json()


def get_committees(client: httpx.Client):
    reg_committees = {}
    dep_committees = {}
    page = 1
    max_pages = 100
    cd_id = 0
    while True and page <= max_pages:
        r = client.get(f"https://velo.ffc.fr/wp-json/sn/cpt/comite?page={page}")
        r.raise_for_status()
        try:
            reg_committee_data = r.json()
            if "region" not in reg_committee_data:
                break
            reg_committee_name = reg_committee_data['region']
            if "extra_data" not in reg_committee_data:
                break
            reg_committee_extra_data = reg_committee_data['extra_data']
            if not isinstance(reg_committee_extra_data, dict):
                break
            if 'id_api' not in reg_committee_extra_data:
                break
            reg_committee_id = reg_committee_extra_data['id_api']
            if not isinstance(reg_committee_id, str):
                break
            if "committees" in reg_committee_data:
                for dep_committee_data in reg_committee_data["committees"]:
                    dep_committee_name = dep_committee_data['post_title']
                    dep_committees[str(cd_id)] = {
                        "name": dep_committee_name,
                        "regional_committee_id": reg_committee_id
                    }
                    cd_id += 1
            reg_committees[reg_committee_id] = {"name": reg_committee_name}
        except KeyError:
            break
        page += 1
    return reg_committees, dep_committees


def get_clubs(
        client: httpx.Client,
        departemental_committees: dict[int, dict[str, str]] | None = None
) -> dict[str, dict[str, str]]:
    if departemental_committees is None:
        departemental_committees = get_committees(client=client)[1]
    clubs = {}
    page = 1
    max_pages = 100
    while True and page <= max_pages:
        r = client.get(f"https://velo.ffc.fr/wp-json/sn/cpt/clubs?page={page}")
        r.raise_for_status()
        try:
            data = r.json()
            if "committees" not in data:
                break
            for dep_committee_data in data['committees']:
                dep_committee_name = dep_committee_data['title']
                norm_dep_committee_name = normalize_string_and_fold_case(dep_committee_name)
                dep_committee_id = None
                for cd_id, cd_data in departemental_committees.items():
                    norm_cd_name = normalize_string_and_fold_case(cd_data['name'])
                    if norm_cd_name == norm_dep_committee_name:
                        dep_committee_id = cd_id
                        break
                if dep_committee_id is None:
                    raise ValueError(f"Departemental committee not found: {dep_committee_name}")
                for club_data in dep_committee_data['items']:
                    club_name = club_data['post_title']
                    club_id = club_data['extra_data']['id_ffc']
                    clubs[club_id] = {
                        "name": club_name,
                        "departemental_committee_id": dep_committee_id
                    }
        except KeyError:
            break
        page += 1
    return clubs


def get_disciplines(client: httpx.Client) -> list[dict[str, str]]:
    r = client.get("https://velo.ffc.fr/wp-json/sn/terms/disciplines")
    r.raise_for_status()
    return r.json()
