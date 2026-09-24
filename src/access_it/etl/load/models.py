from datetime import date
from sqlalchemy import ForeignKey, MetaData, SmallInteger, String, CheckConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Explicit constraint names (makes a later Alembic adoption easier)
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Departement(Base):
    __tablename__ = "departements"

    departement_code: Mapped[str] = mapped_column(String(3), primary_key=True)
    departement_name: Mapped[str] = mapped_column(String())


class RegionalCommittee(Base):
    __tablename__ = "regional_committees"

    regional_committee_id: Mapped[str] = mapped_column(
        String(2),
        primary_key=True
    )
    name: Mapped[str] = mapped_column(String())


class DepartementalCommittee(Base):
    __tablename__ = "departemental_committees"

    departemental_committee_id: Mapped[str] = mapped_column(
        String(4),
        primary_key=True
    )
    name: Mapped[str] = mapped_column(String())
    regional_committee_id: Mapped[str] = mapped_column(
        String(2),
        ForeignKey("regional_committees.regional_committee_id")
    )
    departement_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("departements.departement_code")
    )


class Rider(Base):
    __tablename__ = "riders"

    rider_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    uci_id: Mapped[str] = mapped_column(String(11))
    last_name: Mapped[str] = mapped_column(String())
    first_name: Mapped[str] = mapped_column(String())


class Club(Base):
    __tablename__ = "clubs"
    __table_args__ = (
        CheckConstraint(
            sqltext="min_year BETWEEN 2000 AND 9999",
            name="min_year_range"
        ),
        CheckConstraint(
            sqltext="max_year BETWEEN 2000 AND 9999",
            name="max_year_range"
        ),
        CheckConstraint(
            sqltext="min_year <= max_year",
            name="year_order"
        ),
    )

    club_id: Mapped[str] = mapped_column(String(7), primary_key=True)
    name: Mapped[str] = mapped_column(String())
    departemental_committee_id: Mapped[str] = mapped_column(
        String(4),
        ForeignKey("departemental_committees.departemental_committee_id")
    )
    min_year: Mapped[int] = mapped_column(SmallInteger())
    max_year: Mapped[int] = mapped_column(SmallInteger())
    alternative_names: Mapped[str] = mapped_column(String())


class Race(Base):
    __tablename__ = "races"
    __table_args__ = (
        CheckConstraint(
            sqltext="season BETWEEN 2000 AND 9999",
            name="season_range"
        ),
    )

    race_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    title: Mapped[str] = mapped_column(String())
    categories: Mapped[str] = mapped_column(String(11))
    season: Mapped[int] = mapped_column(SmallInteger())
    discipline: Mapped[str] = mapped_column(String())
    race_date: Mapped[date]
    departement_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("departements.departement_code")
    )
    organization_code: Mapped[str] = mapped_column(String(11))
    race_type: Mapped[str] = mapped_column(String())
    organizer: Mapped[str] = mapped_column(String())
    duration: Mapped[str] = mapped_column(String())
    race_code: Mapped[str] = mapped_column(String(10))


class Ranking(Base):
    __tablename__ = "rankings"
    __table_args__ = (
        CheckConstraint(
            sqltext="finish_rank >= 1",
            name="finish_rank_positive"
        ),
    )

    race_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("races.race_id"),
        primary_key=True
    )
    rider_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("riders.rider_id"),
        primary_key=True,
        index=True
    )
    finish_rank: Mapped[int] = mapped_column(SmallInteger())


class Affiliation(Base):
    __tablename__ = "affiliations"
    __table_args__ = (
        CheckConstraint(
            sqltext="start_date <= end_date",
            name="date_order"
        ),
    )

    affiliation_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    rider_id: Mapped[str] = mapped_column(String(16), ForeignKey("riders.rider_id"))
    club_id: Mapped[str] = mapped_column(String(7), ForeignKey("clubs.club_id"))
    start_date: Mapped[date]
    end_date: Mapped[date]
