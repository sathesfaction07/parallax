"""Causes, rules, severity, ingest, the gate, and a guard on the corpus itself."""

from __future__ import annotations

import csv
from datetime import timedelta

import pytest

from discrepancy_bot.analyse import analyse, payload
from discrepancy_bot.classify import (
    RELATION_NOTES,
    SourceRelation,
    cause_counts,
    classify,
    classify_presence,
    separability,
    why_rules_are_too_late,
)
from discrepancy_bot.config import Settings, provenance
from discrepancy_bot.gate import check
from discrepancy_bot.ingest import parse_time, read_csv, round_trip_loss
from discrepancy_bot.models import (
    Cause,
    Decision,
    Order,
    Pair,
    Pairing,
    Presence,
    Severity,
)
from discrepancy_bot.rules import (
    DEFAULT_RULES,
    Rule,
    apply_rules,
    rules_can_only_subtract,
    suppression_is_a_wager,
    unseparable_is_never_suppressed,
    window_sensitivity_note,
)
from discrepancy_bot.severity import (
    CAUSE_WEIGHT,
    HIGH_AT,
    MEDIUM_AT,
    ORDER_WEIGHT,
    PAIRING_WEIGHT,
    PRESENCE_WEIGHT,
    apply_severity,
    band,
    collisions,
    rank,
    score,
    severity_and_confidence_disagree,
    weights_are_invented,
)

from ..conftest import CORPUS, at, decision, pair


class TestSilenceIsNotDissent:
    def test_python_calls_silence_a_difference(self):
        assert (None != "APPROVED") is True
        assert ("" != "APPROVED") is True

    def test_both_recorded_something(self):
        assert classify_presence(pair("APPROVED", "REJECTED")) is Presence.BOTH

    def test_a_row_that_exists_and_says_nothing(self):
        assert classify_presence(pair("APPROVED", "")) is Presence.RECORDED_EMPTY

    def test_no_row_at_all_is_a_different_thing(self):
        one = Pair(entity="e", left=decision(), pairing=Pairing.ONE_SIDED)
        assert classify_presence(one) is Presence.ONE_SILENT

    def test_an_absent_row_object_is_also_one_silent(self):
        both_present_but_one_absent = Pair(
            entity="e",
            left=decision(),
            right=Decision(entity="e", source="right", row_present=False),
            pairing=Pairing.ONE_TO_ONE,
        )
        assert classify_presence(both_present_but_one_absent) is Presence.ONE_SILENT

    def test_neither_said_anything(self):
        assert classify_presence(pair("", "")) is Presence.NEITHER

    def test_a_silent_side_is_never_reported_as_a_disagreement(self, hour):
        verdict = classify(pair("APPROVED", ""), hour, SourceRelation.MIRROR)
        assert verdict is not None
        assert verdict.cause is Cause.UNSEPARABLE
        assert "silence is not dissent" in verdict.detail
        assert "category error" in verdict.detail


class TestTheSameEvidenceGivesOppositeVerdicts:
    """The finding that surfaced while writing classify.py."""

    def test_undeclared_refuses_to_choose(self, ordered_pair, hour):
        verdict = classify(ordered_pair, hour, SourceRelation.UNDECLARED)
        assert verdict.cause is Cause.UNSEPARABLE
        assert "indistinguishable" in verdict.detail

    def test_mirror_makes_it_a_conflict(self, ordered_pair, hour):
        verdict = classify(ordered_pair, hour, SourceRelation.MIRROR)
        assert verdict.cause is Cause.CONFLICT
        assert "supposed to converge" in verdict.detail

    def test_independent_makes_it_a_transition(self, ordered_pair, hour):
        verdict = classify(ordered_pair, hour, SourceRelation.INDEPENDENT)
        assert verdict.cause is Cause.TRANSITION
        assert "legitimately supersedes" in verdict.detail

    def test_one_pair_three_declarations_three_causes(self, ordered_pair, hour):
        causes = {
            relation: classify(ordered_pair, hour, relation).cause
            for relation in SourceRelation
        }
        assert len(set(causes.values())) == 3, "the declaration decides, not the data"

    def test_every_relation_is_explained(self):
        assert set(RELATION_NOTES) == set(SourceRelation)
        assert "UNSEPARABLE" in RELATION_NOTES[SourceRelation.UNDECLARED]


class TestRaceBeatsTheRelation:
    def test_inside_the_window_no_declaration_can_make_it_a_conflict(self, racing_pair, hour):
        for relation in SourceRelation:
            assert classify(racing_pair, hour, relation).cause is Cause.RACE

    def test_a_race_verdict_records_that_influence_was_established(self, racing_pair, hour):
        verdict = classify(racing_pair, hour, SourceRelation.MIRROR)
        assert verdict.influence.value == "COULD_NOT_HAVE_SEEN"


class TestOrderComesFirst:
    @pytest.mark.parametrize(
        "fixture,expected",
        [("tied_pair", Order.TIED), ("incomparable_pair", Order.INCOMPARABLE),
         ("untimed_pair", Order.UNTIMED)],
    )
    def test_without_a_sequence_no_cause_can_be_named(self, request, fixture, expected, hour):
        verdict = classify(request.getfixturevalue(fixture), hour, SourceRelation.MIRROR)
        assert verdict.cause is Cause.UNSEPARABLE
        assert verdict.order is expected
        assert "cannot be sequenced" in verdict.detail

    def test_the_detail_explains_why_stale_is_also_impossible(self, tied_pair, hour):
        verdict = classify(tied_pair, hour, SourceRelation.MIRROR)
        assert "'stale' means BEHIND" in verdict.detail


class TestACacheMustBeBehindToExplainAnything:
    def test_a_cache_holding_the_older_value_is_lag(self, hour):
        # right is the declared cache, and it decided earlier
        p = pair(left_at=at(9), right_at=at(8))
        verdict = classify(p, hour, SourceRelation.MIRROR, frozenset({"right"}))
        assert verdict.cause is Cause.STALE
        assert "holds the OLDER decision" in verdict.detail
        assert "rests entirely on the DECLARATION" in verdict.detail

    def test_a_cache_holding_the_newer_value_is_not_lag_and_is_not_suppressed(self, hour):
        p = pair(left_at=at(9), right_at=at(15))
        verdict = classify(p, hour, SourceRelation.MIRROR, frozenset({"right"}))
        assert verdict.cause is Cause.UNSEPARABLE
        assert "holds the NEWER value" in verdict.detail
        assert "cannot get ahead of the thing it copies" in verdict.detail
        assert "not suppressed" in verdict.detail

    def test_the_left_side_can_be_the_cache_too(self, hour):
        p = pair(left_at=at(8), right_at=at(9))
        verdict = classify(p, hour, SourceRelation.MIRROR, frozenset({"left"}))
        assert verdict.cause is Cause.STALE

    def test_a_cache_cannot_be_examined_without_a_sequence(self, tied_pair, hour):
        verdict = classify(tied_pair, hour, SourceRelation.MIRROR, frozenset({"right"}))
        assert verdict.cause is Cause.UNSEPARABLE
        assert verdict.order is Order.TIED


class TestNoDifferenceIsNotAGuarantee:
    def test_matching_values_produce_no_verdict(self, hour):
        assert classify(pair("APPROVED", "APPROVED"), hour, SourceRelation.MIRROR) is None

    def test_but_agreement_under_multiplication_still_gets_reported(self, hour):
        agreeing_but_multiplied = pair(
            "APPROVED", "APPROVED", at(9), at(15), Pairing.MULTIPLIED, siblings=1
        )
        verdict = classify(agreeing_but_multiplied, hour, SourceRelation.MIRROR)
        assert verdict is not None, "we chose which row to compare, so agreement means less"
        assert verdict.cause is Cause.UNSEPARABLE

    def test_one_sided_is_reported_even_though_nothing_differs(self, hour):
        one = Pair(entity="e", left=decision(), pairing=Pairing.ONE_SIDED)
        verdict = classify(one, hour, SourceRelation.MIRROR)
        assert verdict is not None
        assert verdict.pairing is Pairing.ONE_SIDED


class TestCountingAndSeparability:
    def test_cause_counts_covers_every_cause(self, ordered_pair, racing_pair, hour):
        verdicts = [
            classify(ordered_pair, hour, SourceRelation.MIRROR),
            classify(racing_pair, hour, SourceRelation.MIRROR),
        ]
        counts = cause_counts([v for v in verdicts if v])
        assert set(counts) == set(Cause)
        assert counts[Cause.CONFLICT] == 1
        assert counts[Cause.RACE] == 1

    def test_separability_reports_the_ratio(self, ordered_pair, tied_pair, hour):
        verdicts = [
            classify(ordered_pair, hour, SourceRelation.MIRROR),
            classify(tied_pair, hour, SourceRelation.MIRROR),
        ]
        named, unseparable, sentence = separability([v for v in verdicts if v])
        assert (named, unseparable) == (1, 1)
        assert "1 of 2" in sentence
        assert "reported, not dropped" in sentence

    def test_nothing_to_explain(self):
        assert separability([]) == (0, 0, "No differences to explain.")

    def test_the_rules_are_named_as_downstream(self):
        note = why_rules_are_too_late()
        assert "downstream of the question" in note
        assert "inspects a pair" in note


class TestRulesCanOnlySubtract:
    @pytest.fixture
    def verdicts(self, ordered_pair, racing_pair, tied_pair, hour):
        return [
            v for v in (
                classify(ordered_pair, hour, SourceRelation.INDEPENDENT),
                classify(racing_pair, hour, SourceRelation.INDEPENDENT),
                classify(tied_pair, hour, SourceRelation.INDEPENDENT),
            ) if v
        ]

    def test_the_count_never_goes_up(self, verdicts):
        assert rules_can_only_subtract(verdicts)
        outcome = apply_rules(verdicts)
        assert outcome.after <= outcome.before

    def test_transitions_and_races_are_removed(self, verdicts):
        outcome = apply_rules(verdicts)
        assert outcome.removed == 2
        assert set(outcome.by_rule()) == {"ordered-supersession", "race-not-reversal"}

    def test_unseparable_survives_every_rule(self, verdicts):
        outcome = apply_rules(verdicts)
        assert {v.cause for v in outcome.kept} == {Cause.UNSEPARABLE}

    def test_no_rule_even_declares_unseparable(self):
        assert unseparable_is_never_suppressed()

    def test_a_rule_that_matched_unseparable_would_still_be_ignored(self, verdicts):
        greedy = (Rule(name="greedy", causes=frozenset(Cause), reason="r", what_it_hides="h"),)
        outcome = apply_rules(verdicts, greedy)
        assert {v.cause for v in outcome.kept} == {Cause.UNSEPARABLE}
        assert outcome.removed == 2

    def test_suppressed_verdicts_carry_the_rule_that_removed_them(self, verdicts):
        outcome = apply_rules(verdicts)
        for verdict, rule_name in outcome.suppressed:
            assert verdict.suppressed_by == rule_name
            assert not verdict.reportable

    def test_no_rules_firing_is_the_only_harmless_case(self, tied_pair, hour):
        only_unseparable = [classify(tied_pair, hour, SourceRelation.MIRROR)]
        outcome = apply_rules(only_unseparable)
        assert outcome.removed == 0
        assert "provably harmless" in outcome.summary()
        assert "nothing was wagered" in suppression_is_a_wager(outcome).lower()

    def test_the_summary_admits_what_a_suppression_becomes(self, verdicts):
        outcome = apply_rules(verdicts)
        assert "indistinguishable from a" in outcome.summary()
        assert "listed rather than deducted" in outcome.summary()

    def test_a_suppression_is_a_bet_that_cannot_be_settled(self, verdicts):
        note = suppression_is_a_wager(apply_rules(verdicts))
        assert "cannot be settled" in note
        assert "stops learning about the thing it filters" in note

    def test_every_rule_declares_what_it_hides(self):
        for rule in DEFAULT_RULES:
            assert rule.reason.strip()
            assert rule.what_it_hides.strip()

    def test_the_race_rule_inherits_the_window(self, hour):
        note = window_sensitivity_note(hour)
        assert "configured" in note
        assert "exactly as good as that number" in note


class TestSeverityIsInvented:
    def _v(self, cause=Cause.CONFLICT, pairing=Pairing.ONE_TO_ONE,
           order=Order.ORDERED, presence=Presence.BOTH):
        from discrepancy_bot.models import Influence, Verdict

        influence = (
            Influence.COULD_NOT_HAVE_SEEN if cause is Cause.RACE else Influence.COULD_HAVE_SEEN
        )
        return Verdict(entity="e", cause=cause, pairing=pairing, presence=presence,
                       order=order, influence=influence)

    def test_the_score_is_the_sum_of_four_weights(self):
        verdict = self._v(cause=Cause.CONFLICT, pairing=Pairing.MULTIPLIED)
        assert score(verdict) == (
            CAUSE_WEIGHT[Cause.CONFLICT] + PAIRING_WEIGHT[Pairing.MULTIPLIED]
            + ORDER_WEIGHT[Order.ORDERED] + PRESENCE_WEIGHT[Presence.BOTH]
        )

    def test_every_enum_member_has_a_weight(self):
        assert set(CAUSE_WEIGHT) == set(Cause)
        assert set(PAIRING_WEIGHT) == set(Pairing)
        assert set(ORDER_WEIGHT) == set(Order)
        assert set(PRESENCE_WEIGHT) == set(Presence)

    @pytest.mark.parametrize(
        "points,expected",
        [(0, Severity.LOW), (MEDIUM_AT - 1, Severity.LOW), (MEDIUM_AT, Severity.MEDIUM),
         (HIGH_AT - 1, Severity.MEDIUM), (HIGH_AT, Severity.HIGH), (999, Severity.HIGH)],
    )
    def test_the_bands_are_thresholds_on_that_sum(self, points, expected):
        assert band(points) is expected

    def test_applying_severity_records_both_the_band_and_the_number(self):
        scored = apply_severity(self._v())
        assert scored.score == score(self._v())
        assert scored.severity is band(scored.score)

    def test_rank_is_descending_and_does_not_depend_on_input_order(self):
        low = self._v(cause=Cause.STALE)
        high = self._v(cause=Cause.CONFLICT, pairing=Pairing.MULTIPLIED)
        forward = [v.score for v in rank([low, high])]
        assert forward == sorted(forward, reverse=True)
        assert [v.score for v in rank([high, low])] == forward

    def test_equal_scores_break_on_entity_so_the_order_is_stable(self):
        from discrepancy_bot.models import Influence, Verdict

        def make(entity):
            return Verdict(entity=entity, cause=Cause.CONFLICT, pairing=Pairing.ONE_TO_ONE,
                           presence=Presence.BOTH, order=Order.ORDERED,
                           influence=Influence.COULD_HAVE_SEEN)

        assert [v.entity for v in rank([make("z"), make("a")])] == ["a", "z"]

    def test_a_weighted_sum_is_not_ordinal(self):
        # CONFLICT+ONE_TO_ONE = 50; UNSEPARABLE+ONE_SIDED+TIED = 30+10+10 = 50
        conflict = self._v(cause=Cause.CONFLICT)
        unseparable = self._v(cause=Cause.UNSEPARABLE, pairing=Pairing.ONE_SIDED,
                              order=Order.TIED)
        assert score(conflict) == score(unseparable) == 50
        found = collisions([conflict, unseparable])
        assert len(found) == 1
        assert found[0].points == 50
        assert "not ordinal" in found[0].summary()
        assert "unrelated problems next to each other" in found[0].summary()

    def test_equal_scores_with_the_same_cause_are_not_a_collision(self):
        same = [self._v(), self._v()]
        assert collisions(same) == []

    def test_severity_and_confidence_are_different_orders(self):
        unexplained = self._v(cause=Cause.UNSEPARABLE, pairing=Pairing.MULTIPLIED,
                              order=Order.UNTIMED)
        count, note = severity_and_confidence_disagree([unexplained])
        assert count == 1
        assert "does not rank how" in note
        assert "two orders and the report shows one" in note

    def test_a_low_scoring_unexplained_pair_is_not_the_confusing_shape(self):
        # UNSEPARABLE alone is 30, which lands on MEDIUM, so use a race to get a LOW
        count, note = severity_and_confidence_disagree([self._v(cause=Cause.RACE)])
        assert count == 0
        assert "No high-severity unexplained" in note

    def test_the_weights_are_labelled_invented(self):
        note = weights_are_invented()
        assert "hand-chosen" in note
        assert "nothing here is calibrated" in note
        assert "the units are nothing" in note


class TestIngestReportsWhatTheFileCouldNotSay:
    def test_a_csv_round_trip_merges_none_and_empty(self):
        first, second, distinguishable = round_trip_loss()
        assert first == second == ""
        assert distinguishable is False

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_blank_times_are_absent_not_invalid(self, raw):
        assert parse_time(raw) == (None, None)

    def test_a_real_timestamp_parses(self):
        parsed, err = parse_time("2025-03-01T09:00:00")
        assert parsed == at(9) and err is None

    def test_an_offset_survives(self):
        parsed, _ = parse_time("2025-03-01T12:00:00+00:00")
        assert parsed.tzinfo is not None

    def test_a_bad_timestamp_returns_the_error_instead_of_raising(self):
        parsed, err = parse_time("not-a-date")
        assert parsed is None
        assert err and "Invalid isoformat" in err

    def test_reading_records_every_kind_of_gap(self, csv_file):
        path = csv_file([
            {"entity": "a", "value": "APPROVED", "decided_at": "2025-03-01T09:00:00"},
            {"entity": "b", "value": "", "decided_at": "2025-03-01T09:00:00"},
            {"entity": "c", "value": "APPROVED", "decided_at": ""},
            {"entity": "d", "value": "APPROVED", "decided_at": "nope"},
            {"entity": "e", "value": "APPROVED", "decided_at": "2025-03-01T09:00:00+00:00"},
            {"entity": "a", "value": "REJECTED", "decided_at": "2025-03-01T10:00:00"},
        ])
        result = read_csv(path, "s")
        assert result.rows == 6
        assert result.blank_values == ["b"]
        assert result.missing_decided_at == ["c", "d"]
        assert [e for e, _ in result.unparseable_times] == ["d"]
        assert result.aware_times == ["e"]
        assert result.duplicate_entities == {"a": 2}
        assert result.mixed_timezone_discipline is True

    def test_a_consistent_file_is_not_flagged_for_timezones(self, csv_file):
        path = csv_file([{"entity": "a", "value": "X", "decided_at": "2025-03-01T09:00:00"}])
        assert read_csv(path, "s").mixed_timezone_discipline is False

    def test_rows_with_no_entity_are_skipped(self, csv_file):
        path = csv_file([{"entity": "", "value": "X"}, {"entity": "a", "value": "X"}])
        assert read_csv(path, "s").rows == 1

    def test_a_missing_required_column_is_refused(self, tmp_path):
        path = tmp_path / "bad.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["entity", "decided_at"])
            writer.writerow(["a", "2025-03-01T09:00:00"])
        with pytest.raises(ValueError, match="missing required column"):
            read_csv(path, "s")

    def test_the_summary_names_each_problem(self, csv_file):
        path = csv_file([
            {"entity": "a", "value": "", "decided_at": ""},
            {"entity": "a", "value": "X", "decided_at": "2025-03-01T09:00:00+00:00"},
            {"entity": "b", "value": "X", "decided_at": "2025-03-01T09:00:00"},
        ])
        summary = read_csv(path, "s").summary()
        assert "cannot be told apart" in summary
        assert "unorderable" in summary
        assert "in ONE file" in summary
        assert "not a single value" in summary

    def test_an_unparseable_timestamp_reaches_the_summary(self, csv_file):
        path = csv_file([{"entity": "a", "value": "X", "decided_at": "the 3rd of March"}])
        assert "could not be parsed" in read_csv(path, "s").summary()

    def test_a_clean_file_summarises_briefly(self, csv_file):
        path = csv_file([{"entity": "a", "value": "X", "decided_at": "2025-03-01T09:00:00"}])
        assert read_csv(path, "s").summary() == "1 rows from s."

    def test_teams_and_read_times_survive(self, csv_file):
        path = csv_file([{
            "entity": "a", "value": "X", "decided_at": "2025-03-01T09:00:00",
            "read_at": "2025-03-02T08:00:00", "team": "T4",
        }])
        row = read_csv(path, "s").decisions[0]
        assert row.team == "T4"
        assert row.read_at is not None


class TestTheGateOnlyFailsOnWhatAProducerCanFix:
    def test_the_corpus_fails_on_its_planted_data_problems(self, corpus_settings):
        gate = check(analyse(corpus_settings))
        assert not gate.passed
        headlines = " ".join(h for h, _ in gate.failures)
        assert "appear more than once" in headlines
        assert "naive timestamps in ONE file" in headlines
        assert "no decision time" in headlines
        assert "could not be parsed" in headlines
        assert "no decision value" in headlines

    def test_clean_files_pass_even_with_unexplained_differences(self, csv_file):
        left = csv_file([{"entity": "a", "value": "APPROVED",
                          "decided_at": "2025-03-01T09:00:00"}], "a.csv")
        csv_file([{"entity": "a", "value": "REJECTED",
                   "decided_at": "2025-03-01T09:00:00"}], "b.csv")
        settings = Settings(data_dir=left.parent, left_file="a.csv", right_file="b.csv")
        result = analyse(settings)
        gate = check(result)
        assert gate.passed
        assert result.unseparable == 1, "there IS an unexplained difference"
        assert "Nothing fixable at source" in gate.summary()

    def test_unseparable_is_reported_and_never_gated(self, csv_file):
        left = csv_file([{"entity": "a", "value": "APPROVED",
                          "decided_at": "2025-03-01T09:00:00"}], "a.csv")
        csv_file([{"entity": "a", "value": "REJECTED",
                   "decided_at": "2025-03-01T09:00:00"}], "b.csv")
        gate = check(analyse(Settings(data_dir=left.parent, left_file="a.csv",
                                      right_file="b.csv")))
        reported = " ".join(h for h, _ in gate.reported)
        assert "UNSEPARABLE" in reported
        assert "UNDECLARED" in reported

    def test_the_undeclared_relation_is_reported_as_an_operator_decision(self, corpus_settings):
        gate = check(analyse(corpus_settings))
        detail = " ".join(d for h, d in gate.reported if "UNDECLARED" in h)
        assert "operator's job" in detail
        assert "declaring it wrongly is worse" in detail

    def test_declaring_a_relation_removes_that_report(self, corpus_settings):
        declared = corpus_settings.model_copy(update={"relation": SourceRelation.MIRROR})
        gate = check(analyse(declared))
        assert not any("UNDECLARED" in h for h, _ in gate.reported)

    def test_suppressions_are_reported_and_never_gated(self, corpus_settings):
        gate = check(analyse(corpus_settings))
        entry = next((d for h, d in gate.reported if "suppressed" in h), None)
        assert entry is not None
        assert "gating on our own filter" in entry

    def test_genuine_simultaneity_is_not_a_defect(self, corpus_settings):
        gate = check(analyse(corpus_settings))
        entry = next((d for h, d in gate.reported if "FULL precision" in h), None)
        assert entry is not None
        assert "Nobody can fix this in an export" in entry

    def test_manufactured_ties_are_diagnostic_only(self, corpus_settings):
        gate = check(analyse(corpus_settings))
        entry = next((d for h, d in gate.reported if "would tie if truncated" in h), None)
        assert entry is not None
        assert "never truncates before comparing" in entry

    def test_the_fail_summary_counts_both_kinds(self, corpus_settings):
        gate = check(analyse(corpus_settings))
        assert "FAIL on" in gate.summary()
        assert "Reported and NOT failed on" not in gate.summary()
        assert "reported and NOT failed on" in gate.summary()


class TestSettings:
    def test_the_window_comes_from_minutes(self):
        assert Settings(propagation_minutes=90).window == timedelta(minutes=90)

    def test_a_negative_window_is_refused(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Settings(propagation_minutes=-1)

    def test_caches_is_a_comma_string_not_a_list_field(self):
        assert Settings(cached_sources="a, b ,c").caches == frozenset({"a", "b", "c"})

    def test_no_caches_by_default(self):
        assert Settings().caches == frozenset()

    def test_paths_are_built_from_the_data_dir(self):
        settings = Settings(data_dir="/tmp/x", left_file="l.csv", right_file="r.csv")
        assert str(settings.left_path) == "/tmp/x/l.csv"
        assert str(settings.right_path) == "/tmp/x/r.csv"

    def test_every_setting_that_matters_has_a_provenance_entry(self):
        names = {name for name, _, _ in provenance()}
        assert {"propagation_minutes", "relation", "cached_sources"} <= names
        for _, source, risk in provenance():
            assert source.strip() and risk.strip()

    def test_the_window_is_labelled_never_measured(self):
        entry = next(p for p in provenance() if p[0] == "propagation_minutes")
        assert "never measured" in entry[1]


class TestTheCorpusStillProducesEveryOutcome:
    """If the corpus stops planting these, the assertions elsewhere go vacuous."""

    def test_the_files_exist_and_only_the_manifest_does(self):
        assert {p.name for p in CORPUS.glob("*.csv")} == {"system_a.csv", "system_b.csv"}

    def test_every_pairing_appears(self, corpus_settings):
        counts = payload(analyse(corpus_settings))["pairing"]
        assert all(counts[p.value] > 0 for p in Pairing)

    def test_every_order_appears(self, corpus_settings):
        counts = payload(analyse(corpus_settings))["order"]
        assert all(counts[o.value] > 0 for o in Order)

    def test_every_cause_appears_under_some_configuration(self, corpus_settings):
        seen: set[str] = set()
        for relation in SourceRelation:
            for cache in ("", "system-b"):
                settings = corpus_settings.model_copy(
                    update={"relation": relation, "cached_sources": cache}
                )
                counts = payload(analyse(settings))["by_cause"]
                seen |= {k for k, v in counts.items() if v}
        assert seen == {c.value for c in Cause}

    def test_the_relation_changes_the_conflict_count(self, corpus_settings):
        conflicts = {}
        for relation in SourceRelation:
            settings = corpus_settings.model_copy(update={"relation": relation})
            conflicts[relation] = analyse(settings).conflicts
        assert conflicts[SourceRelation.MIRROR] > 0
        assert conflicts[SourceRelation.INDEPENDENT] == 0
        assert conflicts[SourceRelation.UNDECLARED] == 0

    def test_the_join_idioms_diverge_on_this_corpus(self, corpus_settings):
        result = payload(analyse(corpus_settings))
        assert result["idioms_agree"] is False
        assert result["dict_pairs"] < result["nested_pairs"]

    def test_truncation_would_cost_orderings(self, corpus_settings):
        result = payload(analyse(corpus_settings))
        assert result["ties_after_truncation"] > result["ties_at_full_precision"]

    def test_the_data_problems_are_all_present(self, corpus_settings):
        result = payload(analyse(corpus_settings))
        assert result["blank_values"]
        assert result["missing_decided_at"]
        assert result["duplicate_entities"]
        assert len(result["mixed_tz_in_one_file"]) == 2

    def test_a_score_collision_exists_under_mirror(self, corpus_settings):
        settings = corpus_settings.model_copy(update={"relation": SourceRelation.MIRROR})
        assert payload(analyse(settings))["score_collisions"] == [50]

    def test_high_severity_unexplained_differences_exist(self, corpus_settings):
        assert payload(analyse(corpus_settings))["high_severity_unexplained"] > 0

    def test_the_headline_refuses_to_give_a_bare_count(self, corpus_settings):
        headline = analyse(corpus_settings).headline()
        assert "UNSEPARABLE" in headline
        assert "rests on the source relation" in headline

    def test_matched_and_differing_add_up_to_the_entities(self, corpus_settings):
        result = analyse(corpus_settings)
        assert result.matched + result.differences == result.entities
