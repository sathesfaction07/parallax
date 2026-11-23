from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from rich.console import Console

from discrepancy_bot import render
from discrepancy_bot.config import Settings
from discrepancy_bot.models import Decision, Pair, Pairing

CORPUS = Path(__file__).parent.parent / "data"


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    """Rich wraps to the terminal, and pytest reports a narrow one.

    Every assertion on output would otherwise depend on the width of whoever's terminal ran the
    suite, so the console is replaced with a fixed-width, colourless one.
    """
    monkeypatch.setattr(render, "console", Console(width=200, no_color=True))


@pytest.fixture
def corpus_settings() -> Settings:
    return Settings(data_dir=CORPUS)


def at(hour: int, minute: int = 0, *, tz: bool = False) -> datetime:
    """A decision time on the corpus's day."""
    kwargs = {"tzinfo": UTC} if tz else {}
    return datetime(2025, 3, 1, hour, minute, **kwargs)


def decision(
    entity: str = "e",
    source: str = "left",
    value: str | None = "APPROVED",
    decided_at: datetime | None = None,
    **kwargs,
) -> Decision:
    return Decision(
        entity=entity, source=source, value=value, decided_at=decided_at, **kwargs
    )


def pair(
    left_value: str | None = "APPROVED",
    right_value: str | None = "REJECTED",
    left_at: datetime | None = None,
    right_at: datetime | None = None,
    pairing: Pairing = Pairing.ONE_TO_ONE,
    siblings: int = 0,
    entity: str = "e",
) -> Pair:
    """A one-to-one pair, unless told otherwise."""
    return Pair(
        entity=entity,
        left=decision(entity, "left", left_value, left_at),
        right=decision(entity, "right", right_value, right_at),
        pairing=pairing,
        siblings=siblings,
    )


@pytest.fixture
def ordered_pair() -> Pair:
    """Six hours apart: ordered, and the second decider could have seen the first."""
    return pair(left_at=at(9), right_at=at(15))


@pytest.fixture
def racing_pair() -> Pair:
    """Four minutes apart: ordered, and nobody could have known."""
    return pair(left_at=at(9), right_at=at(9, 4))


@pytest.fixture
def tied_pair() -> Pair:
    return pair(left_at=at(9), right_at=at(9))


@pytest.fixture
def incomparable_pair() -> Pair:
    return pair(left_at=at(12, tz=True), right_at=at(7))


@pytest.fixture
def untimed_pair() -> Pair:
    return pair(left_at=None, right_at=at(9))


@pytest.fixture
def hour() -> timedelta:
    return timedelta(hours=1)


@pytest.fixture
def csv_file(tmp_path):
    """Write a CSV from rows and hand back the path."""

    def write(rows: list[dict], name: str = "s.csv", columns: tuple[str, ...] | None = None) -> Path:
        cols = columns or ("entity", "value", "decided_at", "read_at", "team")
        path = tmp_path / name
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols)
            writer.writeheader()
            for row in rows:
                writer.writerow({c: row.get(c, "") for c in cols})
        return path

    return write
