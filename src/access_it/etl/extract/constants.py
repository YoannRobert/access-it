"""Pseudo-clubs of the riders without a French club.

Foreign riders, and riders with an individual license of unknown committee,
are attached to these two pseudo-clubs, whose IDs follow the format of the FFC
club IDs. An individual license whose committee is known keeps its FFC ID
(committee ID followed by 800), the pseudo-club of the individual licensees of
that committee.
"""

INDIVIDUAL_NAME = "Individuel"
FOREIGN_NAME = "Etranger"
INDIVIDUAL_CLUB_ID = "9899001"
FOREIGN_CLUB_ID = "9999002"
