"""About page of the dashboard: data, limits, disclaimer, navigation, contact and license."""

import streamlit as st

CONTACT_EMAIL = "accessit.dashboard@gmail.com"

st.title("À propos")

st.markdown(
    "**Access it!** présente les résultats des courses cyclistes amateurs de catégorie Access "
    "(A1 à A4) en Bretagne et en Pays de la Loire : statistiques de saison, classements, fiches "
    "des coureurs et des courses."
)

st.markdown(
    """
### Données

- **Sources** : pages de résultats publiées par la Fédération française de cyclisme (FFC) et
  API de la FFC (clubs et comités).
- **Périmètre** : courses sur route seulement. Les autres disciplines (piste, cyclo-cross, VTT,
  gravel, etc.) sont exclues, de même que les épreuves réservées aux femmes et les courses sans
  classé. Saisons depuis 2023, première année des catégories Access. Seules les courses
  disputées en Bretagne et en Pays de la Loire sont enregistrées : les coureurs d'autres régions
  ne sont suivis que sur ces courses.
- **Fraîcheur** : le tableau de bord vérifie quatre fois par jour (0 h, 6 h, 12 h et 18 h, heure
  de Paris) si de nouvelles données sont disponibles. Les calculs sont faits au lendemain de la
  dernière course enregistrée.

### Limites

- La FFC ne publie pas la catégorie d'un coureur dans une course mixte. Elle est déduite de son
  historique et de ses résultats par une heuristique imparfaite : elle peut être fausse, mal
  datée ou inconnue. Tous les calculs par catégorie en dépendent (challenge, points de montée,
  changements de catégorie, filtres).
- Le club d'un coureur est déduit de ses résultats. Il peut être inconnu. Les licenciés sans
  club apparaissent sous un club « Individuel » rattaché à leur comité.
- Le challenge régional et les points de montée sont des reconstitutions. Ils peuvent différer
  des classements publiés par le comité régional ou la FFC.
- Le rang est la place dans la course, toutes catégories confondues, sans reclassement par
  catégorie.

### Avertissement

Ce site est un exercice personnel d'apprentissage de la data et de l'IA, sans lien avec la FFC
ni avec ses comités. Les données sont fournies sans garantie d'exactitude ni d'exhaustivité.
L'auteur décline toute responsabilité quant à leur utilisation. Seuls les résultats publiés par
la FFC font foi.

### Navigation

Dans les tableaux, sélectionnez une ligne puis cliquez sur « Voir la fiche » pour ouvrir la fiche
du coureur ou de la course. L'adresse d'une fiche peut être partagée.
"""
)

st.markdown(
    f"""
### Contact et données personnelles

Pour signaler une erreur, ou demander que votre nom n'apparaisse plus :
[{CONTACT_EMAIL}](mailto:{CONTACT_EMAIL}). Toute demande sera traitée.

### Licence

Le code source est publié sous licence MIT sur
[GitHub](https://github.com/YoannRobert/access-it). Cette licence ne porte que sur le code, pas
sur les résultats sportifs, qui proviennent de la FFC.
"""
)
