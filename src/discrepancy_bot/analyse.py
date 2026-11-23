"""Tying it together: read two sources, pair, classify, filter, score.

The order of operations here IS the argument. Pairing happens before comparison, presence before
difference, order before cause, and the rules run last -- where they can be seen and counted
rather than where they quietly decide things.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .classify import SourceRelation, cause_counts, classify, separability
from .config import Settings
from .ingest import IngestResult, read_csv
from .models import Cause, Pairing, Verdict
from .ordering import TieRisk, order_counts, tie_risk
from .pairing import IdiomComparison, cardinality_counts, compare_idioms, pair_up
from .rules import DEFAULT_RULES, RuleOutcome, apply_rules
from .severity import collisions, rank, severity_and_confidence_disagree


@dataclass
class Analysis:
    """Everything one run established, including what it could not."""

    left: IngestResult
    right: IngestResult
    entities: int
    matched: int
    verdicts: list[Verdict] = field(default_factory=list)
    reported: list[Verdict] = field(default_factory=list)
    idioms: IdiomComparison | None = None
    ties: TieRisk | None = None
    rule_outcome: RuleOutcome | None = None
    relation: SourceRelation = SourceRelation.UNDECLARED

    @property
    def differences(self) -> int:
        return len(self.verdicts)

    @property
    def by_cause(self) -> dict[Cause, int]:
        return cause_counts(self.verdicts)

    @property
    def unseparable(self) -> int:
        return self.by_cause[Cause.UNSEPARABLE]

    @property
    def conflicts(self) -> int:
        return self.by_cause[Cause.CONFLICT]

    @property
    def suppressed(self) -> int:
        return self.rule_outcome.removed if self.rule_outcome else 0

    @property
    def undefined_comparisons(self) -> int:
        """Entities where asking "do these differ" was not a meaningful question."""
        return sum(1 for v in self.verdicts if v.pairing is not Pairing.ONE_TO_ONE)

    def headline(self) -> str:
        """The one sentence that should not be able to mislead.

        It refuses to say a number of discrepancies without saying how many of them are
        unexplained, because the second number is what decides whether the first is useful.
        """
        named, unsep, _ = separability(self.verdicts)
        return (
            f"{self.entities} entities, {self.matched} recorded the same value, "
            f"{self.differences} differ. Of those, {named} have a named cause and {unsep} are "
            f"UNSEPARABLE. {self.conflicts} are called CONFLICT, which is the only cause worth "
            f"anyone's morning -- and that count rests on the source relation being declared "
            f"{self.relation}."
        )


def analyse(settings: Settings) -> Analysis:
    """Run the whole pipeline over two CSV files."""
    left = read_csv(settings.left_path, settings.left_name)
    right = read_csv(settings.right_path, settings.right_name)

    pairs = pair_up(left.decisions, right.decisions)
    verdicts: list[Verdict] = []
    matched = 0
    for pair in pairs:
        verdict = classify(pair, settings.window, settings.relation, settings.caches)
        if verdict is None:
            matched += 1
        else:
            verdicts.append(verdict)

    outcome = apply_rules(verdicts, DEFAULT_RULES) if settings.apply_rules else None
    reported = rank(list(outcome.kept) if outcome else verdicts)

    return Analysis(
        left=left,
        right=right,
        entities=len(pairs),
        matched=matched,
        verdicts=verdicts,
        reported=reported,
        idioms=compare_idioms(left.decisions, right.decisions),
        ties=tie_risk(pairs, settings.truncate_unit),
        rule_outcome=outcome,
        relation=settings.relation,
    )


def payload(analysis: Analysis) -> dict:
    """A machine-readable summary, for CI to assert on."""
    pairing_counts = {k.value: v for k, v in cardinality_counts(
        pair_up(analysis.left.decisions, analysis.right.decisions)
    ).items()}
    confusing, _ = severity_and_confidence_disagree(analysis.verdicts)
    return {
        "entities": analysis.entities,
        "matched": analysis.matched,
        "differences": analysis.differences,
        "by_cause": {k.value: v for k, v in analysis.by_cause.items()},
        "unseparable": analysis.unseparable,
        "conflicts": analysis.conflicts,
        "relation": analysis.relation.value,
        "pairing": pairing_counts,
        "order": {k.value: v for k, v in order_counts(
            pair_up(analysis.left.decisions, analysis.right.decisions)
        ).items()},
        "undefined_comparisons": analysis.undefined_comparisons,
        "idioms_agree": analysis.idioms.idioms_agree if analysis.idioms else None,
        "dict_pairs": analysis.idioms.dict_pairs if analysis.idioms else None,
        "nested_pairs": analysis.idioms.nested_pairs if analysis.idioms else None,
        "ties_at_full_precision": analysis.ties.tied_at_full if analysis.ties else None,
        "ties_after_truncation": analysis.ties.tied_after if analysis.ties else None,
        "suppressed": analysis.suppressed,
        "suppressed_by_rule": analysis.rule_outcome.by_rule() if analysis.rule_outcome else {},
        "reported": len(analysis.reported),
        "blank_values": sorted(set(analysis.left.blank_values) | set(analysis.right.blank_values)),
        "missing_decided_at": sorted(
            set(analysis.left.missing_decided_at) | set(analysis.right.missing_decided_at)
        ),
        "mixed_tz_in_one_file": [
            r.source for r in (analysis.left, analysis.right) if r.mixed_timezone_discipline
        ],
        "duplicate_entities": sorted(
            set(analysis.left.duplicate_entities) | set(analysis.right.duplicate_entities)
        ),
        "score_collisions": [c.points for c in collisions(analysis.verdicts)],
        "high_severity_unexplained": confusing,
    }
