"""Generate the two-source corpus.

Hand-authored, not randomised. Every entity below exists to produce one specific outcome, and the
name says which -- so a reader can check the tool's claim against the input by eye rather than by
trusting a seed.

This script OWNS `data/`. Anything in there that is not in MANIFEST gets removed, because a stale
fixture left behind by an earlier convention is the kind of thing that parses cleanly and quietly
changes every count.
"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).parent
MANIFEST = ("system_a.csv", "system_b.csv")

COLUMNS = ("entity", "value", "decided_at", "read_at", "team")

# (entity, value, decided_at, read_at, team)
LEFT: tuple[tuple[str, str, str, str, str], ...] = (
    ("e01-agree", "APPROVED", "2025-03-01T09:00:00", "2025-03-02T08:00:00", "T1"),
    ("e02-ordered-far", "APPROVED", "2025-03-01T09:00:00", "2025-03-02T08:00:00", "T1"),
    ("e03-race", "APPROVED", "2025-03-01T09:00:00", "2025-03-02T08:00:00", "T1"),
    ("e04-tied", "APPROVED", "2025-03-01T09:00:00", "2025-03-02T08:00:00", "T1"),
    ("e05-naive-vs-aware", "APPROVED", "2025-03-01T12:00:00+00:00", "2025-03-02T08:00:00", "T1"),
    ("e06-untimed", "APPROVED", "", "2025-03-02T08:00:00", "T1"),
    ("e07-blank-right", "APPROVED", "2025-03-01T09:00:00", "2025-03-02T08:00:00", "T1"),
    ("e08-left-only", "APPROVED", "2025-03-01T09:00:00", "2025-03-02T08:00:00", "T1"),
    ("e10-two-teams", "APPROVED", "2025-03-01T09:00:00", "2025-03-02T08:00:00", "T1"),
    ("e11-cache", "APPROVED", "2025-03-01T09:00:00", "2025-03-02T08:00:00", "T1"),
    ("e12-same-instant", "APPROVED", "2025-03-01T12:00:00+00:00", "2025-03-02T08:00:00", "T1"),
    ("e13-day-truncation", "APPROVED", "2025-03-01T09:00:00", "2025-03-02T08:00:00", "T1"),
    ("e14-unparseable", "APPROVED", "not-a-date", "2025-03-02T08:00:00", "T1"),
    ("e15-agree-multiplied", "APPROVED", "2025-03-01T09:00:00", "2025-03-02T08:00:00", "T1"),
    ("e16-cache-ahead", "APPROVED", "2025-03-01T09:00:00", "2025-03-02T08:00:00", "T1"),
)

RIGHT: tuple[tuple[str, str, str, str, str], ...] = (
    # Same value: the pair matches, and there is nothing to explain.
    ("e01-agree", "APPROVED", "2025-03-01T11:00:00", "2025-03-02T08:05:00", "T9"),
    # Six hours apart with a one-hour window: ordered, and the second decider could have seen
    # the first. This is the pair whose cause depends entirely on the declared relation.
    ("e02-ordered-far", "REJECTED", "2025-03-01T15:00:00", "2025-03-02T08:05:00", "T9"),
    # Four minutes apart: ordered, and nobody could have known. A race, not a reversal.
    ("e03-race", "REJECTED", "2025-03-01T09:04:00", "2025-03-02T08:05:00", "T9"),
    # Identical decision times: no sequence exists at all.
    ("e04-tied", "REJECTED", "2025-03-01T09:00:00", "2025-03-02T08:05:00", "T9"),
    # Naive against the left side's aware: Python refuses to compare them.
    ("e05-naive-vs-aware", "REJECTED", "2025-03-01T07:00:00", "2025-03-02T08:05:00", "T9"),
    ("e06-untimed", "REJECTED", "2025-03-01T10:00:00", "2025-03-02T08:05:00", "T9"),
    # An empty value: a row that exists and says nothing.
    ("e07-blank-right", "", "2025-03-01T10:00:00", "2025-03-02T08:05:00", "T9"),
    # e08 deliberately absent here; e09 deliberately absent from the left.
    ("e09-right-only", "REJECTED", "2025-03-01T10:00:00", "2025-03-02T08:05:00", "T9"),
    # Two teams, one entity -- the brief's "multiple teams" case, which is a PAIRING problem.
    ("e10-two-teams", "REJECTED", "2025-03-01T15:00:00", "2025-03-02T08:05:00", "T1"),
    ("e10-two-teams", "APPROVED", "2025-03-01T16:00:00", "2025-03-02T08:05:00", "T2"),
    # The cache holds the OLDER decision -- which is what lag looks like.
    ("e11-cache", "REJECTED", "2025-03-01T08:00:00", "2025-03-02T08:05:00", "T9"),
    # ...and this one holds a NEWER value than its source, which lag cannot explain.
    ("e16-cache-ahead", "REJECTED", "2025-03-01T15:00:00", "2025-03-02T08:05:00", "T9"),
    # Same instant as the left, written with an offset instead of in UTC.
    ("e12-same-instant", "APPROVED", "2025-03-01T07:00:00-05:00", "2025-03-02T08:05:00", "T9"),
    # Eight hours apart, so ordered -- until someone truncates to the day.
    ("e13-day-truncation", "REJECTED", "2025-03-01T17:00:00", "2025-03-02T08:05:00", "T9"),
    ("e14-unparseable", "REJECTED", "2025-03-01T10:00:00", "2025-03-02T08:05:00", "T9"),
    # Two rows that AGREE with the left. Agreement under multiplication is not agreement:
    # we still chose which row to compare.
    ("e15-agree-multiplied", "APPROVED", "2025-03-01T15:00:00", "2025-03-02T08:05:00", "T1"),
    ("e15-agree-multiplied", "APPROVED", "2025-03-01T16:00:00", "2025-03-02T08:05:00", "T2"),
)

PLANTED = {
    "e01-agree": "values match, so nothing to explain",
    "e02-ordered-far": "ORDERED + COULD_HAVE_SEEN -- cause depends on the declared relation",
    "e03-race": "RACE: ordered, but inside the propagation window",
    "e04-tied": "TIED: identical decision times, so no sequence",
    "e05-naive-vs-aware": "INCOMPARABLE: aware against naive",
    "e06-untimed": "UNTIMED: no decision time on the left",
    "e07-blank-right": "RECORDED_EMPTY: a row that exists and says nothing",
    "e08-left-only": "ONE_SIDED: absent from the right",
    "e09-right-only": "ONE_SIDED: absent from the left",
    "e10-two-teams": "MULTIPLIED: two teams, so the comparison is undefined",
    "e11-cache": "STALE, but only when the right source is declared a cache",
    "e12-same-instant": "one instant, two strings -- and the values agree",
    "e13-day-truncation": "ordered at full precision, tied once truncated to the day",
    "e14-unparseable": "a timestamp that will not parse",
    "e15-agree-multiplied": "values agree AND pairing is multiplied",
    "e16-cache-ahead": "a declared cache holding a NEWER value, which lag cannot explain",
}


def write(path: Path, rows: tuple[tuple[str, str, str, str, str], ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        writer.writerows(rows)


def prune(directory: Path) -> list[str]:
    """Remove anything this script did not write."""
    removed = []
    for path in sorted(directory.glob("*.csv")):
        if path.name not in MANIFEST:
            path.unlink()
            removed.append(path.name)
    return removed


def main() -> None:
    HERE.mkdir(parents=True, exist_ok=True)
    removed = prune(HERE)
    write(HERE / "system_a.csv", LEFT)
    write(HERE / "system_b.csv", RIGHT)

    entities = {r[0] for r in LEFT} | {r[0] for r in RIGHT}
    print(f"wrote {len(LEFT)} rows to system_a.csv and {len(RIGHT)} rows to system_b.csv")
    print(f"{len(entities)} entities, {len(PLANTED)} of them planted for a specific outcome")
    if removed:
        print(f"pruned {len(removed)} file(s) this generator did not write: {', '.join(removed)}")
    assert entities == set(PLANTED), f"manifest drift: {entities ^ set(PLANTED)}"


if __name__ == "__main__":
    main()
