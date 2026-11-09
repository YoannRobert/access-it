---
title: Access it!
emoji: 🚴
colorFrom: yellow
colorTo: blue
sdk: docker
app_port: 7860
license: mit
tags:
- streamlit
pinned: false
short_description: Courses cyclistes Access - classements et statistiques
---

# Access it!

Classements et statistiques des courses cyclistes amateurs de catégorie **Access** (A1 à A4)
en **Bretagne** et en **Pays de la Loire**, à partir des résultats publiés par la Fédération
française de cyclisme (FFC).

## Pages

- **Saison** : courses par mois, par département et par catégories, coureurs les plus titrés,
  changements de catégorie.
- **Classements** : challenge régional des Pays de la Loire, points de montée, clubs.
- **Coureur** : recherche par nom, puis fiche (résultats, statistiques et points par saison,
  catégories et clubs successifs, forme récente).
- **Confrontations** : courses communes de deux coureurs et qui a fini devant l'autre.
- **Course** : liste des courses filtrée par période, région, départements et catégories,
  puis classement.

Dans les tableaux, sélectionnez une ligne puis cliquez sur « Voir la fiche » pour ouvrir
la fiche du coureur ou de la course.

## Données

- **Sources** : pages de résultats de la FFC (courses sur route, catégories Access) et API de
  la FFC (clubs et comités).
- **Saisons** : depuis 2023, première saison des catégories Access.
- **Fraîcheur** : le tableau de bord affiche le dernier instantané de la base ; il vérifie
  quatre fois par jour (0 h, 6 h, 12 h et 18 h, heure de Paris) si un nouvel instantané
  existe. Les calculs sont faits à la date de référence, lendemain de la dernière course
  enregistrée.

## Limites

- La catégorie d'un coureur dans une course mixte n'est pas publiée par la FFC : elle est
  déduite de son historique et peut être inconnue. Son club peut l'être aussi.
- Le challenge régional n'existe que pour les Pays de la Loire.
- Les épreuves réservées aux femmes et les courses sans classé sont exclues.
- Le rang est la place absolue dans la course, sans reclassement par catégorie.

Projet personnel, sans lien avec la FFC : seuls les résultats publiés par la FFC font foi.

## Technique

Tableau de bord Streamlit dans une image Docker, sur ce Space. Il lit un instantané de la
base PostgreSQL déposé sur le stockage objet de Neon ; le code est synchronisé depuis GitHub
par un workflow GitHub Actions. Collecte, ETL, architecture et installation : voir le dépôt
[YoannRobert/access-it](https://github.com/YoannRobert/access-it).

## Licence

MIT.