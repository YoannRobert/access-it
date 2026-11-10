"""Small fake snapshot of the database for the page tests of the dashboard.

Two seasons, two covered regions and a few riders, consistent between the
tables (keys, dates, contiguous categories), so that every page of the
dashboard can run:

- r1 and r2 share the last name DUPONT (homonyms), in two clubs of Loire-Atlantique;
- r4 rides for a club of Bretagne, which has no regional challenge;
- r5 has no club (unknown club);
- r6 changes category at the start of 2026 (category change);
- the last race is on 2026-09-20: the reference date is 2026-09-21.
"""

import pandas as pd

from datetime import date

from access_it.common.regions import BRETAGNE, PAYS_DE_LA_LOIRE
from access_it.etl.extract.constants import INDIVIDUAL_CLUB_ID

LAST_SEASON = 2026

REGIONAL_COMMITTEES = pd.DataFrame({
    "regional_committee_id": ["52", "53", INDIVIDUAL_CLUB_ID[:2]],
    "name": [PAYS_DE_LA_LOIRE, BRETAGNE, "INDIVIDUEL"],
})
DEPARTEMENTAL_COMMITTEES = pd.DataFrame({
    "departemental_committee_id": ["5244", "5285", "5335", "9899"],
    "name": ["CD 44", "CD 85", "CD 35", "INDIVIDUEL"],
    "regional_committee_id": ["52", "52", "53", "98"],
    "departement_code": ["44", "85", "35", "99"],
})
DEPARTEMENTS = pd.DataFrame({
    "departement_code": ["35", "44", "85", "99"],
    "departement_name": ["Ille-et-Vilaine", "Loire-Atlantique", "Vendée", "Autre"],
})
CLUBS = pd.DataFrame({
    "club_id": ["5244001", "5244002", "5285001", "5335001", INDIVIDUAL_CLUB_ID],
    "name": ["VC NANTES", "UC SAINT-NAZAIRE", "VS LA ROCHE", "VC RENNES", "INDIVIDUEL"],
    "departemental_committee_id": ["5244", "5244", "5285", "5335", "9899"],
    "min_year": [2023] * 5,
    "max_year": [LAST_SEASON] * 5,
    "alternative_names": [""] * 5,
})
RIDERS = pd.DataFrame({
    "rider_id": ["r1", "r2", "r3", "r4", "r5", "r6"],
    "uci_id": ["10000000001", "10000000002", "10000000003", "10000000004", "", ""],
    "last_name": ["DUPONT", "DUPONT", "MARTIN", "LE GOFF", "BERNARD", "PETIT"],
    "first_name": ["Jean", "Paul", "Luc", "Yann", "Marc", "Hugo"],
})

_RACES = [
    # race_id, title, categories, race_date, departement_code
    ("c1", "Grand Prix de Nantes", "A1,A2", date(2025, 5, 4), "44"),
    ("c2", "Circuit de Rennes", "A3,A4", date(2025, 6, 15), "35"),
    ("c3", "Prix de Saint-Herblain", "A1,A2,A3,A4", date(2026, 4, 12), "44"),
    ("c4", "Boucles vendéennes", "A2,A3", date(2026, 5, 10), "85"),
    ("c5", "Prix de Vitré", "A1,A2", date(2026, 6, 7), "35"),
    ("c6", "Nocturne de Nantes", "A3,A4", date(2026, 9, 20), "44"),
]
RACES = pd.DataFrame({
    "race_id": [r[0] for r in _RACES],
    "title": [r[1] for r in _RACES],
    "categories": [r[2] for r in _RACES],
    "season": [r[3].year for r in _RACES],
    "discipline": ["Route"] * len(_RACES),
    "race_date": [r[3] for r in _RACES],
    "departement_code": [r[4] for r in _RACES],
    "organization_code": [f"C{index:010d}" for index in range(len(_RACES))],
    "race_type": ["1.24.1"] * len(_RACES),
    "organizer": ["Club organisateur"] * len(_RACES),
    "duration": ["1 jour"] * len(_RACES),
    "race_code": [f"{index:03d}" for index in range(len(_RACES))],
})

_RANKINGS = {
    "c1": ["r1", "r2", "r3", "r6"],
    "c2": ["r4", "r5", "r3"],
    "c3": ["r2", "r1", "r3", "r6", "r5"],
    "c4": ["r3", "r6", "r2"],
    "c5": ["r4", "r1", "r2"],
    "c6": ["r6", "r3", "r5", "r1"],
}
RANKINGS = pd.DataFrame([
    {"race_id": race_id, "rider_id": rider_id, "finish_rank": rank}
    for race_id, rider_ids in _RANKINGS.items()
    for rank, rider_id in enumerate(rider_ids, start=1)
])

RIDER_CATEGORIES = pd.DataFrame({
    "rider_id": ["r1", "r2", "r3", "r4", "r5", "r6", "r6"],
    "start_date": [date(2025, 1, 1)] * 6 + [date(2026, 1, 1)],
    "rider_category": [1, 2, 3, 2, 4, 4, 3],
})
AFFILIATIONS = pd.DataFrame({
    "rider_id": ["r1", "r2", "r3", "r4", "r6"],
    "start_date": [date(2025, 1, 1)] * 5,
    "club_id": ["5244001", "5244002", "5285001", "5335001", "5244001"],
})

TABLES = {
    "regional_committees": REGIONAL_COMMITTEES,
    "departemental_committees": DEPARTEMENTAL_COMMITTEES,
    "departements": DEPARTEMENTS,
    "clubs": CLUBS,
    "riders": RIDERS,
    "races": RACES,
    "rankings": RANKINGS,
    "rider_categories": RIDER_CATEGORIES,
    "affiliations": AFFILIATIONS,
}
