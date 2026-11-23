"""Lining up one entity's rows across two sources.

This runs BEFORE any comparison, and it is where the brief's "multiple teams working on the
same entity" actually goes wrong. The brief proposes to handle that with exception rules, but a
rule inspects a pair -- and by the time a pair exists, the damage is done and invisible.

Two join idioms people write without thinking fail in OPPOSITE directions, which `compare_idioms`
demonstrates on real data rather than asserting.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .models import Decision, Pair, Pairing


def index_by_entity(rows: list[Decision]) -> dict[str, Decision]:
    """The dict-index join, written the way it is usually written.

    `{r.entity: r for r in rows}` keeps the LAST row for each entity and drops the rest, with
    no error and no trace. Given two teams' decisions on one entity, one of them ceases to
    exist here.
    """
    return {r.entity: r for r in rows}


def nested_loop_join(
    left: list[Decision], right: list[Decision]
) -> list[tuple[Decision, Decision]]:
    """The nested-loop join, also written the way it is usually written.

    This one keeps everything, which means for an entity with two rows on a side it emits two
    pairs. The count of pairs is then larger than the count of entities, so a report that says
    "we found N discrepancies" is counting something other than entities.
    """
    return [(a, b) for a in left for b in right if a.entity == b.entity]


@dataclass(frozen=True)
class IdiomComparison:
    """What the two idioms did to the same input."""

    entities: int
    left_rows: int
    right_rows: int
    dict_pairs: int
    nested_pairs: int
    dropped_by_dict: tuple[str, ...]
    multiplied_in_nested: tuple[str, ...]

    @property
    def idioms_agree(self) -> bool:
        return self.dict_pairs == self.nested_pairs

    def summary(self) -> str:
        if self.idioms_agree:
            return (
                f"Both idioms produce {self.dict_pairs} pairs from {self.entities} entities. "
                "They agree here, which is not a property of the idioms -- it is a property of "
                "this input having one row per entity per side."
            )
        return (
            f"{self.entities} entities. The dict-index join produces {self.dict_pairs} pairs and "
            f"DROPS a decision for {len(self.dropped_by_dict)} of them; the nested-loop join "
            f"produces {self.nested_pairs} pairs, MULTIPLYING {len(self.multiplied_in_nested)} of "
            "them. One idiom undercounts, the other overcounts, and neither says which it did."
        )


def compare_idioms(left: list[Decision], right: list[Decision]) -> IdiomComparison:
    """Run both joins on one input and report how they diverge."""
    entities = {r.entity for r in left} | {r.entity for r in right}
    left_counts: dict[str, int] = defaultdict(int)
    right_counts: dict[str, int] = defaultdict(int)
    for r in left:
        left_counts[r.entity] += 1
    for r in right:
        right_counts[r.entity] += 1

    dropped = tuple(sorted(e for e in entities if left_counts[e] > 1 or right_counts[e] > 1))
    nested = nested_loop_join(left, right)
    multiplied = tuple(sorted(e for e in entities if left_counts[e] * right_counts[e] > 1))

    dict_left, dict_right = index_by_entity(left), index_by_entity(right)
    dict_pairs = len(set(dict_left) & set(dict_right))

    return IdiomComparison(
        entities=len(entities),
        left_rows=len(left),
        right_rows=len(right),
        dict_pairs=dict_pairs,
        nested_pairs=len(nested),
        dropped_by_dict=dropped,
        multiplied_in_nested=multiplied,
    )


def pair_up(left: list[Decision], right: list[Decision]) -> list[Pair]:
    """Line up both sides, and RECORD the cardinality instead of assuming it.

    Every entity present in either source appears in the output exactly once. An entity with
    several rows on a side becomes a single MULTIPLIED pair carrying a sibling count -- not
    several pairs, because the entity has one situation, not several.
    """
    by_entity: dict[str, tuple[list[Decision], list[Decision]]] = defaultdict(lambda: ([], []))
    for r in left:
        by_entity[r.entity][0].append(r)
    for r in right:
        by_entity[r.entity][1].append(r)

    pairs: list[Pair] = []
    for entity in sorted(by_entity):
        ls, rs = by_entity[entity]
        if not ls or not rs:
            pairs.append(
                Pair(
                    entity=entity,
                    left=ls[0] if ls else None,
                    right=rs[0] if rs else None,
                    pairing=Pairing.ONE_SIDED,
                )
            )
            continue
        siblings = (len(ls) - 1) + (len(rs) - 1)
        pairing = Pairing.MULTIPLIED if siblings else Pairing.ONE_TO_ONE
        pairs.append(
            Pair(entity=entity, left=ls[0], right=rs[0], pairing=pairing, siblings=siblings)
        )
    return pairs


def cardinality_counts(pairs: list[Pair]) -> dict[Pairing, int]:
    counts = dict.fromkeys(Pairing, 0)
    for p in pairs:
        counts[p.pairing] += 1
    return counts


def comparison_is_defined(pair: Pair) -> tuple[bool, str]:
    """Whether asking "do these two values differ" means anything for this pair."""
    if pair.pairing is Pairing.ONE_SIDED:
        return False, (
            "Only one source has a row for this entity, so there is no second value to compare "
            "with. This is not agreement and it is not disagreement."
        )
    if pair.pairing is Pairing.MULTIPLIED:
        return False, (
            f"{pair.siblings} extra row(s) exist for this entity, so 'the decision in that "
            "system' is not a single value. Whichever row we compare, we chose it, and the "
            "choice is not visible in the result."
        )
    return True, "Exactly one row each side, so a comparison is defined."
