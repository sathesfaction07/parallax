"""Models, pairing, ordering, influence -- the four preconditions."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from discrepancy_bot.influence import (
    assess,
    sensitivity,
    verdict_depends_on_the_guess,
    window_is_a_guess,
)
from discrepancy_bot.models import (
    CAUSE_NOTES,
    ORDER_NOTES,
    PAIRING_NOTES,
    Cause,
    Decision,
    Influence,
    Order,
    Pair,
    Pairing,
    Presence,
    Severity,
    Verdict,
)
from discrepancy_bot.ordering import (
    classify_order,
    comparable,
    force_comparable,
    order_counts,
    same_instant,
    same_text,
    stable_sort_demo,
    tie_risk,
)
from discrepancy_bot.pairing import (
    cardinality_counts,
    compare_idioms,
    comparison_is_defined,
    index_by_entity,
    nested_loop_join,
    pair_up,
)

from ..conftest import at, decision, pair


class TestEnumsCarryTheirExplanations:
    def test_every_cause_has_a_note_and_what_it_needs(self):
        assert set(CAUSE_NOTES) == set(Cause)
        for cause in Cause:
            what, needs = CAUSE_NOTES[cause]
            assert what.strip() and needs.strip()

    def test_every_pairing_and_order_is_explained(self):
        assert set(PAIRING_NOTES) == set(Pairing)
        assert set(ORDER_NOTES) == set(Order)
        assert all(v.strip() for v in PAIRING_NOTES.values())
        assert all(v.strip() for v in ORDER_NOTES.values())

    def test_unseparable_is_described_as_neither_error_nor_clean(self):
        _, note = CAUSE_NOTES[Cause.UNSEPARABLE]
        assert "NOT an error" in note
        assert "not a clean bill of health" in note

    def test_conflict_is_the_only_one_worth_waking_for(self):
        _, note = CAUSE_NOTES[Cause.CONFLICT]
        assert "only one worth" in note

    @pytest.mark.parametrize("cause", list(Cause))
    def test_causes_are_strings(self, cause):
        assert cause == cause.value


class TestDecision:
    def test_a_row_that_is_absent_cannot_carry_anything(self):
        with pytest.raises(ValidationError, match="cannot carry a value"):
            Decision(entity="e", source="s", value="APPROVED", row_present=False)

    def test_an_absent_row_with_a_time_is_also_refused(self):
        with pytest.raises(ValidationError):
            Decision(entity="e", source="s", decided_at=at(9), row_present=False)

    def test_an_absent_row_saying_nothing_is_fine(self):
        assert Decision(entity="e", source="s", row_present=False).said_nothing

    @pytest.mark.parametrize("value", [None, "", "   ", "\t"])
    def test_blank_of_any_shape_counts_as_saying_nothing(self, value):
        assert decision(value=value).said_nothing

    @pytest.mark.parametrize("value", ["APPROVED", "0", "false", "-"])
    def test_anything_else_is_a_decision(self, value):
        assert not decision(value=value).said_nothing

    def test_timed_is_about_the_decision_not_the_reading(self):
        assert not Decision(entity="e", source="s", read_at=at(9)).timed
        assert decision(decided_at=at(9)).timed

    def test_entity_and_source_cannot_be_empty(self):
        with pytest.raises(ValidationError):
            Decision(entity="", source="s")
        with pytest.raises(ValidationError):
            Decision(entity="e", source="")

    def test_frozen(self):
        with pytest.raises(ValidationError):
            decision().value = "X"


class TestPairRefusesToMisdescribeItself:
    def test_one_sided_with_both_sides_is_refused(self):
        with pytest.raises(ValidationError, match="ONE_SIDED requires"):
            Pair(
                entity="e",
                left=decision(),
                right=decision(source="right"),
                pairing=Pairing.ONE_SIDED,
            )

    @pytest.mark.parametrize("pairing", [Pairing.ONE_TO_ONE, Pairing.MULTIPLIED])
    def test_a_missing_side_needs_the_one_sided_label(self, pairing):
        with pytest.raises(ValidationError, match="requires both sides"):
            Pair(entity="e", left=decision(), pairing=pairing, siblings=1)

    def test_multiplied_without_siblings_is_a_contradiction(self):
        with pytest.raises(ValidationError, match="siblings must be"):
            Pair(entity="e", left=decision(), right=decision(source="r"),
                 pairing=Pairing.MULTIPLIED, siblings=0)

    def test_siblings_cannot_be_negative(self):
        with pytest.raises(ValidationError):
            Pair(entity="e", left=decision(), right=decision(source="r"),
                 pairing=Pairing.MULTIPLIED, siblings=-1)

    def test_values_differ_is_only_about_the_two_strings(self):
        assert pair("APPROVED", "REJECTED").values_differ
        assert not pair("APPROVED", "APPROVED").values_differ

    def test_a_one_sided_pair_does_not_differ_because_there_is_no_comparison(self):
        one = Pair(entity="e", left=decision(), pairing=Pairing.ONE_SIDED)
        assert one.values_differ is False


class TestVerdictWillNotClaimMoreThanItsEvidence:
    def _verdict(self, **kwargs):
        base = {
            "entity": "e",
            "cause": Cause.CONFLICT,
            "pairing": Pairing.ONE_TO_ONE,
            "presence": Presence.BOTH,
            "order": Order.ORDERED,
            "influence": Influence.COULD_HAVE_SEEN,
        }
        return Verdict(**{**base, **kwargs})

    @pytest.mark.parametrize("order", [Order.TIED, Order.INCOMPARABLE, Order.UNTIMED])
    def test_transition_without_order_is_refused(self, order):
        with pytest.raises(ValidationError, match="that needs ORDER"):
            self._verdict(cause=Cause.TRANSITION, order=order)

    @pytest.mark.parametrize(
        "influence", [Influence.COULD_HAVE_SEEN, Influence.UNKNOWABLE]
    )
    def test_race_without_established_non_influence_is_refused(self, influence):
        with pytest.raises(ValidationError, match="that needs INFLUENCE"):
            self._verdict(cause=Cause.RACE, influence=influence)

    def test_race_with_could_not_have_seen_is_fine(self):
        assert self._verdict(cause=Cause.RACE,
                             influence=Influence.COULD_NOT_HAVE_SEEN).cause is Cause.RACE

    def test_unscored_must_not_carry_a_score(self):
        with pytest.raises(ValidationError, match="UNSCORED must not carry"):
            self._verdict(score=10)

    def test_a_band_without_its_score_is_refused(self):
        with pytest.raises(ValidationError, match="computed from a score"):
            self._verdict(severity=Severity.HIGH)

    def test_reportable_excludes_suppressed_and_stale(self):
        assert self._verdict().reportable
        assert not self._verdict(suppressed_by="some-rule").reportable
        assert not self._verdict(cause=Cause.STALE).reportable

    def test_unseparable_is_reportable_because_that_is_the_point(self):
        assert self._verdict(cause=Cause.UNSEPARABLE).reportable


class TestTheTwoJoinIdiomsFailOppositely:
    """The finding: one drops a decision, the other multiplies rows."""

    @pytest.fixture
    def two_teams(self):
        left = [decision("e1", "L"), decision("e2", "L")]
        right = [
            decision("e1", "R", "REJECTED", team="T1"),
            decision("e1", "R", "APPROVED", team="T2"),
            decision("e2", "R", "APPROVED", team="T1"),
        ]
        return left, right

    def test_dict_index_join_silently_keeps_only_the_last_row(self, two_teams):
        _, right = two_teams
        indexed = index_by_entity(right)
        assert len(indexed) == 2, "three rows became two"
        assert indexed["e1"].team == "T2", "T1's decision ceased to exist"

    def test_nested_loop_join_produces_more_pairs_than_entities(self, two_teams):
        left, right = two_teams
        joined = nested_loop_join(left, right)
        assert len(joined) == 3
        assert len({a.entity for a, _ in joined}) == 2

    def test_the_two_idioms_disagree_and_say_so(self, two_teams):
        result = compare_idioms(*two_teams)
        assert result.idioms_agree is False
        assert result.dict_pairs == 2
        assert result.nested_pairs == 3
        assert result.dropped_by_dict == ("e1",)
        assert result.multiplied_in_nested == ("e1",)
        assert "undercounts" in result.summary()
        assert "overcounts" in result.summary()

    def test_when_they_agree_it_is_a_property_of_the_input(self):
        left = [decision("e1", "L")]
        right = [decision("e1", "R")]
        result = compare_idioms(left, right)
        assert result.idioms_agree
        assert "property of the idioms" in result.summary()
        assert "property of" in result.summary()

    def test_pair_up_gives_one_row_per_entity_and_records_cardinality(self, two_teams):
        pairs = pair_up(*two_teams)
        assert [p.entity for p in pairs] == ["e1", "e2"]
        by_entity = {p.entity: p for p in pairs}
        assert by_entity["e1"].pairing is Pairing.MULTIPLIED
        assert by_entity["e1"].siblings == 1
        assert by_entity["e2"].pairing is Pairing.ONE_TO_ONE

    def test_pair_up_is_sorted_so_output_does_not_depend_on_input_order(self, two_teams):
        left, right = two_teams
        forward = [p.entity for p in pair_up(left, right)]
        backward = [p.entity for p in pair_up(list(reversed(left)), list(reversed(right)))]
        assert forward == backward

    def test_an_entity_on_one_side_only_is_one_sided(self):
        pairs = pair_up([decision("only-left", "L")], [decision("only-right", "R")])
        assert {p.entity: p.pairing for p in pairs} == {
            "only-left": Pairing.ONE_SIDED,
            "only-right": Pairing.ONE_SIDED,
        }

    def test_cardinality_counts_covers_every_kind(self):
        pairs = pair_up(
            [decision("a", "L"), decision("b", "L"), decision("c", "L")],
            [decision("a", "R"), decision("b", "R"), decision("b", "R"), decision("d", "R")],
        )
        counts = cardinality_counts(pairs)
        assert set(counts) == set(Pairing)
        assert counts[Pairing.ONE_TO_ONE] == 1
        assert counts[Pairing.MULTIPLIED] == 1
        assert counts[Pairing.ONE_SIDED] == 2


class TestWhenAComparisonIsEvenDefined:
    def test_one_to_one_is_defined(self):
        defined, why = comparison_is_defined(pair())
        assert defined
        assert "one row each side" in why

    def test_one_sided_is_neither_agreement_nor_disagreement(self):
        one = Pair(entity="e", left=decision(), pairing=Pairing.ONE_SIDED)
        defined, why = comparison_is_defined(one)
        assert not defined
        assert "not agreement and it is not disagreement" in why

    def test_multiplied_admits_the_row_was_chosen(self):
        defined, why = comparison_is_defined(pair(pairing=Pairing.MULTIPLIED, siblings=2))
        assert not defined
        assert "not a single value" in why
        assert "we chose it" in why


class TestTimestampsCannotAlwaysBeCompared:
    def test_aware_against_naive_raises_in_python(self):
        with pytest.raises(TypeError, match="offset-naive and offset-aware"):
            _ = at(12, tz=True) < at(7)

    def test_comparable_detects_it_without_raising(self):
        assert comparable(at(9), at(10))
        assert comparable(at(9, tz=True), at(10, tz=True))
        assert not comparable(at(12, tz=True), at(7))

    def test_forcing_the_comparison_makes_it_run_and_reports_the_shift(self):
        a, b, offset = force_comparable(at(12, tz=True), at(7))
        assert offset == timedelta(0), "UTC's own offset is zero"
        assert a > b, "it compares now, which is the whole danger"
        assert a.tzinfo is None and b.tzinfo is None

    def test_the_shift_is_real_when_the_offset_is_not_utc(self):
        from datetime import datetime, timezone

        # 07:00-05:00 IS 12:00Z. Stripped of its offset it becomes 07:00, five hours earlier,
        # which is enough to invert an order.
        est = datetime(2025, 3, 1, 7, tzinfo=timezone(timedelta(hours=-5)))
        assert est == at(12, tz=True)
        a, b, offset = force_comparable(est, at(9))
        assert offset == timedelta(hours=-5)
        assert a < b, "the same instant now sorts BEFORE 09:00 instead of after"

    def test_forcing_a_comparable_pair_changes_nothing(self):
        a, b, offset = force_comparable(at(9), at(10))
        assert (a, b, offset) == (at(9), at(10), None)

    def test_a_real_offset_is_reported(self):
        from datetime import datetime, timezone

        est = datetime(2025, 3, 1, 7, tzinfo=timezone(timedelta(hours=-5)))
        _, _, offset = force_comparable(est, at(7))
        assert offset == timedelta(hours=-5)

    def test_one_instant_two_strings(self):
        from datetime import UTC, datetime, timezone

        utc = datetime(2025, 3, 1, 12, tzinfo=UTC)
        est = datetime(2025, 3, 1, 7, tzinfo=timezone(timedelta(hours=-5)))
        assert same_instant(utc, est) is True
        assert same_text(utc, est) is False

    def test_same_instant_is_false_when_they_cannot_be_compared(self):
        assert same_instant(at(12, tz=True), at(12)) is False


class TestOrderIsOftenAbsent:
    def test_ordered(self, ordered_pair):
        order, detail = classify_order(ordered_pair)
        assert order is Order.ORDERED
        assert "left decided first" in detail
        assert "SEQUENCE and nothing more" in detail

    def test_tied(self, tied_pair):
        order, detail = classify_order(tied_pair)
        assert order is Order.TIED
        assert "no sequence" in detail
        assert "whichever arrived first in the input" in detail

    def test_incomparable(self, incomparable_pair):
        order, detail = classify_order(incomparable_pair)
        assert order is Order.INCOMPARABLE
        assert "refuses to compare" in detail

    def test_untimed(self, untimed_pair):
        order, detail = classify_order(untimed_pair)
        assert order is Order.UNTIMED
        assert "read time will not substitute" in detail

    def test_a_one_sided_pair_is_untimed(self):
        one = Pair(entity="e", left=decision(decided_at=at(9)), pairing=Pairing.ONE_SIDED)
        order, detail = classify_order(one)
        assert order is Order.UNTIMED
        assert "no second time" in detail

    def test_the_later_side_is_named_correctly(self):
        order, detail = classify_order(pair(left_at=at(15), right_at=at(9)))
        assert order is Order.ORDERED
        assert "right decided first" in detail

    def test_order_counts_covers_every_kind(
        self, ordered_pair, tied_pair, incomparable_pair, untimed_pair
    ):
        counts = order_counts([ordered_pair, tied_pair, incomparable_pair, untimed_pair])
        assert set(counts) == set(Order)
        assert all(v == 1 for v in counts.values())


class TestPrecisionLossManufacturesTies:
    def test_day_truncation_turns_orderable_pairs_into_ties(self):
        pairs = [pair(left_at=at(9), right_at=at(17)) for _ in range(3)]
        risk = tie_risk(pairs, "day")
        assert risk.tied_at_full == 0
        assert risk.tied_after == 3
        assert risk.manufactured == 3
        assert "the format threw it away" in risk.summary()

    def test_hour_truncation_is_less_destructive(self):
        pairs = [pair(left_at=at(9), right_at=at(17))]
        assert tie_risk(pairs, "hour").manufactured == 0
        assert tie_risk(pairs, "day").manufactured == 1

    def test_minute_truncation(self):
        pairs = [pair(left_at=at(9, 0), right_at=at(9, 0))]
        assert tie_risk(pairs, "minute").tied_after == 1

    def test_genuine_ties_are_not_blamed_on_truncation(self, tied_pair):
        risk = tie_risk([tied_pair], "day")
        assert risk.tied_at_full == 1
        assert risk.manufactured == 0

    def test_an_unknown_unit_is_refused(self):
        with pytest.raises(ValueError, match="unknown unit"):
            tie_risk([pair(left_at=at(9), right_at=at(10))], "fortnight")

    def test_untimed_and_incomparable_pairs_are_excluded(self, untimed_pair, incomparable_pair):
        assert tie_risk([untimed_pair, incomparable_pair], "day").pairs == 0

    def test_no_timed_pairs_says_so(self):
        assert "nothing to lose" in tie_risk([], "day").summary()


class TestATieHandsTheVerdictToWhoeverLoadedTheFile:
    def test_input_order_decides_who_was_latest(self):
        rows = [
            decision("e", "A", "APPROVED", at(9)),
            decision("e", "B", "REJECTED", at(9)),
        ]
        demo = stable_sort_demo(rows)
        assert demo.as_loaded == "B=REJECTED"
        assert demo.reversed_load == "A=APPROVED"
        assert demo.verdict_flips
        assert "opposite conclusions" in demo.summary()
        assert "stable" in demo.summary()

    def test_no_tie_means_input_order_is_irrelevant(self):
        rows = [
            decision("e", "A", "APPROVED", at(9)),
            decision("e", "B", "REJECTED", at(15)),
        ]
        demo = stable_sort_demo(rows)
        assert not demo.verdict_flips
        assert "does not decide anything" in demo.summary()

    def test_nothing_timed(self):
        demo = stable_sort_demo([decision("e", "A", "APPROVED", None)])
        assert demo.as_loaded == "nothing timed"
        assert not demo.verdict_flips


class TestInfluenceIsNotSequence:
    def test_far_apart_means_the_second_could_have_seen_the_first(self, ordered_pair, hour):
        call = assess(ordered_pair, hour)
        assert call.influence is Influence.COULD_HAVE_SEEN
        assert call.gap == timedelta(hours=6)
        assert call.is_a_reversal
        assert "possible, not established" in call.detail
        assert "Being able to see something is not seeing it" in call.detail

    def test_inside_the_window_nobody_overturned_anybody(self, racing_pair, hour):
        call = assess(racing_pair, hour)
        assert call.influence is Influence.COULD_NOT_HAVE_SEEN
        assert call.gap == timedelta(minutes=4)
        assert not call.is_a_reversal
        assert "nobody overturned anybody" in call.detail
        assert "ordering is not enough" in call.detail

    @pytest.mark.parametrize("fixture", ["tied_pair", "incomparable_pair", "untimed_pair"])
    def test_without_order_influence_is_unknowable(self, request, fixture, hour):
        call = assess(request.getfixturevalue(fixture), hour)
        assert call.influence is Influence.UNKNOWABLE
        assert call.gap is None
        assert "no 'later' decision" in call.detail

    def test_the_boundary_is_strictly_greater_than(self, hour):
        exactly = pair(left_at=at(9), right_at=at(10))
        assert assess(exactly, hour).influence is Influence.COULD_NOT_HAVE_SEEN
        just_over = pair(left_at=at(9), right_at=at(10, 1))
        assert assess(just_over, hour).influence is Influence.COULD_HAVE_SEEN

    def test_a_zero_window_makes_everything_a_possible_reversal(self, racing_pair):
        assert assess(racing_pair, timedelta(0)).influence is Influence.COULD_HAVE_SEEN

    def test_the_gap_is_absolute_so_side_order_does_not_matter(self, hour):
        forward = assess(pair(left_at=at(9), right_at=at(15)), hour)
        backward = assess(pair(left_at=at(15), right_at=at(9)), hour)
        assert forward.gap == backward.gap == timedelta(hours=6)

    def test_the_window_is_labelled_a_guess(self, hour):
        note = window_is_a_guess(hour)
        assert "CONFIGURED, not measured" in note
        assert "argued with" in note

    def test_sensitivity_reasks_at_every_window(self, racing_pair):
        windows = [timedelta(minutes=1), timedelta(hours=1)]
        answers = sensitivity(racing_pair, windows)
        assert [w for w, _ in answers] == windows
        assert answers[0][1] is Influence.COULD_HAVE_SEEN
        assert answers[1][1] is Influence.COULD_NOT_HAVE_SEEN

    def test_a_verdict_that_moves_with_the_guess_is_flagged(self, racing_pair):
        assert verdict_depends_on_the_guess(
            racing_pair, [timedelta(minutes=1), timedelta(hours=1)]
        )

    def test_a_verdict_that_holds_everywhere_is_not(self, ordered_pair):
        assert not verdict_depends_on_the_guess(
            ordered_pair, [timedelta(minutes=1), timedelta(minutes=5)]
        )
