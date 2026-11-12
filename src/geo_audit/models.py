"""Immutable parser and interval records; parsing is not billing acceptance."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Ping:
    ping_id: str
    driver_id: str
    timestamp: datetime
    received_at: datetime
    lon: float
    lat: float
    is_synthetic: bool


@dataclass(frozen=True)
class ParsedRow:
    source_row: int
    raw: tuple[tuple[str, str | None], ...]
    ping: Ping | None
    driver_id: str | None
    timestamp: datetime | None
    reasons: tuple[str, ...]

    @property
    def assignable(self) -> bool:
        return self.driver_id is not None and self.timestamp is not None


@dataclass(frozen=True)
class DayInterval:
    day: date
    start: float
    end: float
