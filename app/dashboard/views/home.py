"""Home page of the dashboard: short presentation of the project and links to the pages."""

import streamlit as st

PAGES = [
    (
        "views/season.py", "Saison",
        "Le bilan d'une saison, avec les courses, les coureurs les plus titrés et les "
        "changements de catégorie.",
    ),
    (
        "views/rankings.py", "Classements",
        "Le challenge régional des Pays de la Loire, les points de montée et le classement des "
        "clubs.",
    ),
    (
        "views/rider.py", "Coureur",
        "La fiche d'un coureur, avec ses résultats, sa forme récente, ses points par saison, ses "
        "catégories et ses clubs successifs.",
    ),
    (
        "views/head_to_head.py", "Confrontations",
        "Deux coureurs face à face, avec leurs courses communes et qui a fini devant l'autre.",
    ),
    (
        "views/race.py", "Course",
        "Les courses d'une période et le classement de chacune.",
    ),
]

st.title("Access it!")
st.markdown(
    "Les résultats des courses cyclistes amateurs Access (A1 à A4) en Bretagne et en Pays de la "
    "Loire, depuis 2023."
)

columns = st.columns(2)
for index, (page, label, description) in enumerate(PAGES):
    with columns[index % 2].container(border=True):
        st.page_link(page, label=f"**{label}**")
        st.markdown(description)

st.markdown("Projet personnel, sans lien avec la FFC. Données, limites et contact :")
st.page_link("views/about.py", label="À propos")
