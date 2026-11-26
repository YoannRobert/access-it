"""Settings of the recent form and of the forecasts shown by the dashboard.

A top N is a finish rank up to TOP_N, counted on the LAST_RACES last races of the
WINDOW_MONTHS months before the reference date. MISSING_PLACE is the best place given by the
model to a rider without recent result (MISSING_PLACE of access_it.features.examples, which
the dashboard cannot import); it is shown as an empty cell.
"""

TOP_N = 10
LAST_RACES = 10
WINDOW_MONTHS = 6
MISSING_PLACE = 100
