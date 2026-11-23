"""Reading decisions out of CSV, and reporting what the file could not say.

CSV is the interchange format the brief asks for, and it destroys the distinction this tool most
needs. `csv.writer` writes `None` as an empty field; `csv.DictReader` reads both an empty field
and a missing one back as `""`. So "no decision was made" and "a decision was recorded as blank"
arrive identical, and `"" != "APPROVED"` is `True`, which means a naive comparison calls that a
disagreement.

Nothing here fixes that. It is not fixable at read time -- the information left when the file was
written. What is possible is to say so, per row, and to count it.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .models import Decision

REQUIRED = ("entity", "value")
OPTIONAL = ("decided_at", "read_at", "team")


@dataclass
class IngestResult:
    """The rows that parsed, and everything the file failed to say."""

    source: str
    decisions: list[Decision] = field(default_factory=list)
    blank_values: list[str] = field(default_factory=list)
    unparseable_times: list[tuple[str, str]] = field(default_factory=list)
    naive_times: list[str] = field(default_factory=list)
    aware_times: list[str] = field(default_factory=list)
    missing_decided_at: list[str] = field(default_factory=list)
    duplicate_entities: dict[str, int] = field(default_factory=dict)

    @property
    def rows(self) -> int:
        return len(self.decisions)

    @property
    def mixed_timezone_discipline(self) -> bool:
        """True when one file contains both aware and naive decision times.

        Worth its own flag: within a single source this is a data quality problem, and ACROSS
        two sources it is the thing that makes ordering raise.
        """
        return bool(self.naive_times) and bool(self.aware_times)

    def summary(self) -> str:
        parts = [f"{self.rows} rows from {self.source}"]
        if self.blank_values:
            parts.append(
                f"{len(self.blank_values)} with a blank decision -- which after a CSV round trip "
                "cannot be told apart from a decision that was never recorded"
            )
        if self.missing_decided_at:
            parts.append(f"{len(self.missing_decided_at)} with no decision time, so unorderable")
        if self.mixed_timezone_discipline:
            parts.append(
                f"{len(self.aware_times)} aware and {len(self.naive_times)} naive timestamps in "
                "ONE file, so some comparisons within this source will refuse to run"
            )
        if self.duplicate_entities:
            parts.append(
                f"{len(self.duplicate_entities)} entities appear more than once, so 'the decision "
                "in this system' is not a single value for them"
            )
        if self.unparseable_times:
            parts.append(f"{len(self.unparseable_times)} timestamps could not be parsed")
        return "; ".join(parts) + "."


def parse_time(raw: str | None) -> tuple[datetime | None, str | None]:
    """Parse an ISO timestamp, returning the failure rather than raising.

    An unparseable timestamp is data to report, not an exception to crash on -- a batch of ten
    thousand rows should not stop because one of them has a typo.
    """
    if raw is None or raw.strip() == "":
        return None, None
    try:
        return datetime.fromisoformat(raw.strip()), None
    except ValueError as exc:
        return None, str(exc)


def read_csv(path: Path, source: str) -> IngestResult:
    """Read one source's decisions, recording what each row failed to carry."""
    result = IngestResult(source=source)
    seen: dict[str, int] = {}

    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name} is missing required column(s): {', '.join(missing)}")

        for row in reader:
            entity = (row.get("entity") or "").strip()
            if not entity:
                continue

            seen[entity] = seen.get(entity, 0) + 1
            raw_value = row.get("value")
            value = raw_value.strip() if raw_value else raw_value
            if value is None or value == "":
                result.blank_values.append(entity)

            decided_at, err = parse_time(row.get("decided_at"))
            if err:
                result.unparseable_times.append((entity, err))
            if decided_at is None:
                result.missing_decided_at.append(entity)
            elif decided_at.tzinfo is None:
                result.naive_times.append(entity)
            else:
                result.aware_times.append(entity)

            read_at, _ = parse_time(row.get("read_at"))
            team = (row.get("team") or "").strip() or None

            result.decisions.append(
                Decision(
                    entity=entity,
                    source=source,
                    value=value,
                    decided_at=decided_at,
                    read_at=read_at,
                    team=team,
                )
            )

    result.duplicate_entities = {e: n for e, n in seen.items() if n > 1}
    return result


def round_trip_loss() -> tuple[str, str, bool]:
    """Demonstrate the loss rather than assert it.

    Writes `None` and `""` through the csv module and reads them back. Returns both values and
    whether they survived as distinguishable.
    """
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["entity", "value"])
    writer.writerow(["e1", None])
    writer.writerow(["e2", ""])
    back = list(csv.DictReader(io.StringIO(buf.getvalue())))
    first, second = back[0]["value"], back[1]["value"]
    return first, second, first != second
