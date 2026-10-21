"""Remove from the database the riders that are no longer in the riders file.

A rider disappears from the file when its rider_id changes, typically when a
rider without UCI ID (or on the red list) appears later with a UCI ID: the
database then still holds the old rider_id, with its results, affiliations and
categories, next to the new one. These stale riders block the load (see
checks.py); this module deletes them with every row referring to them.

Safeguards:
- dry run by default: nothing is deleted unless `apply` is True;
- rows of riders still present in the file are never deleted, even when they
  are missing from the files (e.g. results dropped by the transform step):
  they are only reported for a manual review;
- nothing is done when more riders than `max_riders` are stale, which rather
  points to a faulty transform step than to a few riders changing identifiers.
"""

from dataclasses import dataclass, field

import pandas as pd

from sqlalchemy import Engine, Table, delete, func, select

from access_it.etl.load.checks import NO_MISSING_ROWS, find_missing_rows
from access_it.etl.load.models import Base

MAX_STALE_RIDERS = 20
RIDERS = Base.metadata.tables["riders"]


class TooManyStaleRiders(Exception):
    """Raised when more riders than allowed would be deleted."""


@dataclass
class PruneReport:
    """What was (or would be, in a dry run) deleted from the database."""

    applied: bool
    stale_riders: list[tuple] = field(default_factory=list)  # (rider_id, uci_id, last, first)
    deleted_rows: dict[str, int] = field(default_factory=dict)  # table name -> rows
    unexplained_missing_rows: dict[str, int] = field(default_factory=dict)  # left untouched


def tables_referring_to_riders() -> list[Table]:
    """Tables having a foreign key to riders.rider_id."""
    return [
        table
        for table in Base.metadata.sorted_tables
        if any(fk.column.table is RIDERS for fk in table.foreign_keys)
    ]


def prune_stale_riders(
        engine: Engine,
        riders: pd.DataFrame,
        frames: dict[str, pd.DataFrame],
        apply: bool = False,
        max_riders: int = MAX_STALE_RIDERS
    ) -> PruneReport:
    """Delete (or count, in a dry run) the stale riders and every row referring to them.

    Everything is done in a single transaction.

    Args:
        engine: Engine of the database.
        riders: Riders file.
        frames: Files of the tables referring to riders, keyed by table
            name, used to report the missing rows that are not deleted.
        apply: Whether to delete (False: dry run, rows are only counted).
        max_riders: Maximum number of stale riders.

    Returns:
        What was (or would be) deleted.

    Raises:
        TooManyStaleRiders: If more than `max_riders` riders are stale
            (nothing is deleted).
    """
    report = PruneReport(applied=apply)
    with engine.begin() as connection:
        count, stale_riders = find_missing_rows(
            connection,
            RIDERS,
            riders,
            columns=["rider_id", "uci_id", "last_name", "first_name"],
            limit=max_riders + 1,
        )
        if count > max_riders:
            raise TooManyStaleRiders(
                f"{count} riders of the database are missing from the riders file "
                f"(maximum {max_riders}): nothing was deleted. This rather points to a "
                f"faulty transform step; check the riders file first."
            )
        report.stale_riders = stale_riders
        stale_ids = [rider_id for rider_id, *_ in stale_riders]

        # Rows referring to the stale riders first (foreign keys), then the riders
        for table in [*tables_referring_to_riders(), RIDERS]:
            condition = table.c.rider_id.in_(stale_ids)
            if apply:
                deleted = connection.execute(delete(table).where(condition)).rowcount
            else:
                deleted = connection.execute(
                    select(func.count()).select_from(table).where(condition)
                ).scalar_one()
            report.deleted_rows[table.name] = deleted

        # Missing rows of riders still in the file: reported, never deleted
        for table in tables_referring_to_riders():
            if table.name not in NO_MISSING_ROWS or table.name not in frames:
                continue
            missing, _ = find_missing_rows(connection, table, frames[table.name], limit=0)
            remaining = missing - (0 if apply else report.deleted_rows[table.name])
            if remaining > 0:
                report.unexplained_missing_rows[table.name] = remaining
    return report


def format_report(report: PruneReport) -> str:
    """Human-readable summary of a PruneReport."""
    verb = "Deleted" if report.applied else "Would delete (dry run)"
    lines = [f"{len(report.stale_riders)} stale rider(s) in the database:"]
    for rider_id, uci_id, last_name, first_name in report.stale_riders:
        lines.append(f"  {rider_id}  {last_name} {first_name}  (UCI ID field: {uci_id!r})")
    lines.append(f"{verb}:")
    for table_name, rows in report.deleted_rows.items():
        lines.append(f"  {table_name}: {rows} row(s)")
    for table_name, rows in report.unexplained_missing_rows.items():
        lines.append(
            f"Warning: {rows} row(s) of {table_name} missing from the file belong to riders "
            f"still in the file: not deleted, review them manually."
        )
    if not report.applied and report.stale_riders:
        lines.append("Run again with --apply to delete these rows.")
    if report.applied:
        lines.append("Then run the load again: python scripts/load.py")
    return "\n".join(lines)
