"""The commands, and the sentences they are required to say.

Rich folds long words inside table cells, so `flat` collapses whitespace before matching. Prose
that must survive verbatim lives outside table cells in render.py for exactly this reason.
"""

from __future__ import annotations

import json
import re

import pytest
from typer.testing import CliRunner

from discrepancy_bot.cli import app

from ..conftest import CORPUS

runner = CliRunner()


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


@pytest.fixture(scope="module", autouse=True)
def wide_console():
    """Render tables wide enough that no cell wraps. These tests check WHAT the tool says;
    where a narrow terminal breaks a cell is layout, and it differs by platform (rich gives
    legacy Windows consoles one column less), which made a phrase test fail only there."""
    from discrepancy_bot import cli, render

    consoles = [cli.console, render.console]
    saved = [c.width for c in consoles]
    for c in consoles:
        c.width = 200
    yield
    for c, width in zip(consoles, saved, strict=True):
        c.width = width


def run(*args: str, env: dict | None = None):
    base = {"DB_DATA_DIR": str(CORPUS)}
    base.update(env or {})
    return runner.invoke(app, list(args), env=base)


class TestCauses:
    @pytest.fixture(scope="class")
    def output(self):
        return run("causes")

    def test_it_runs(self, output):
        assert output.exit_code == 0

    def test_it_states_the_spine(self, output):
        assert "FOUR causes, ONE observable pair" in flat(output.stdout)

    def test_it_names_all_five_outcomes(self, output):
        for name in ("CONFLICT", "TRANSITION", "RACE", "STALE", "UNSEPARABLE"):
            assert name in output.stdout

    def test_it_says_what_separates_them_is_not_in_the_pair(self, output):
        assert "not in the pair" in flat(output.stdout)

    def test_it_places_the_briefs_rules_downstream(self, output):
        assert "downstream of the question" in flat(output.stdout)

    def test_it_shows_the_relation_flipping_the_verdict(self, output):
        text = flat(output.stdout)
        assert "MIRROR" in text and "INDEPENDENT" in text and "UNDECLARED" in text
        assert "appears nowhere in the rows" in text


class TestPair:
    @pytest.fixture(scope="class")
    def output(self):
        return run("pair")

    def test_it_runs(self, output):
        assert output.exit_code == 0

    def test_it_shows_both_idioms(self, output):
        text = flat(output.stdout)
        assert "r.entity: r for r in rows" in text
        assert "keeps the LAST row per entity" in text
        assert "keeps everything" in text

    def test_it_says_one_undercounts_and_one_overcounts(self, output):
        text = flat(output.stdout)
        assert "undercounts" in text and "overcounts" in text

    def test_it_lists_the_undefined_comparisons(self, output):
        text = flat(output.stdout)
        assert "not defined" in text
        assert "e10-two-teams" in output.stdout

    def test_it_counts_every_pairing_kind(self, output):
        for kind in ("ONE_TO_ONE", "ONE_SIDED", "MULTIPLIED"):
            assert kind in output.stdout


class TestOrder:
    @pytest.fixture(scope="class")
    def output(self):
        return run("order")

    def test_it_runs(self, output):
        assert output.exit_code == 0

    def test_it_names_every_way_order_can_fail(self, output):
        for kind in ("ORDERED", "TIED", "INCOMPARABLE", "UNTIMED"):
            assert kind in output.stdout

    def test_it_explains_that_python_refuses_the_comparison(self, output):
        assert "REFUSES to compare" in flat(output.stdout)

    def test_it_reports_what_truncation_would_cost(self, output):
        assert "the format threw it away" in flat(output.stdout)

    def test_it_shows_input_order_deciding_the_verdict(self, output):
        text = flat(output.stdout)
        assert "opposite conclusions" in text
        assert "order the rows happened to arrive in" in text


class TestInfluence:
    def test_the_table_separates_sequence_from_influence(self):
        output = run("influence")
        assert output.exit_code == 0
        assert "sequence is not influence" in flat(output.stdout).lower()
        assert "Being able to see something is not seeing it" in flat(output.stdout)

    def test_a_race_is_named_as_nobody_overturning_anybody(self):
        output = run("influence")
        assert "nobody overturned anybody" in flat(output.stdout)

    def test_one_entity_gets_the_sensitivity_table(self):
        output = run("influence", "e03-race")
        assert output.exit_code == 0
        text = flat(output.stdout)
        assert "COULD_NOT_HAVE_SEEN" in text
        assert "asked at other windows" in text
        assert "verdict about the guess" in text

    def test_even_a_six_hour_gap_flips_at_a_wide_enough_window(self):
        # This is the pair that looks like an obvious reversal. Widen the window to a day and
        # it becomes a race, which is the point: the verdict is about the window.
        output = run("influence", "e02-ordered-far")
        text = flat(output.stdout)
        assert "COULD_HAVE_SEEN" in text
        assert "verdict about the guess" in text

    def test_a_verdict_that_holds_everywhere_says_so(self):
        # A tie has no sequence, so no window can make influence knowable.
        output = run("influence", "e04-tied")
        text = flat(output.stdout)
        assert "UNKNOWABLE" in text
        assert "holds across every window" in text

    def test_the_window_is_called_a_guess(self):
        output = run("influence", "e03-race")
        assert "CONFIGURED, not measured" in flat(output.stdout)

    def test_an_unknown_entity_exits_one(self):
        output = run("influence", "no-such-entity")
        assert output.exit_code == 1


class TestRules:
    @pytest.fixture(scope="class")
    def output(self):
        return run("rules", "--relation", "INDEPENDENT")

    def test_it_runs(self, output):
        assert output.exit_code == 0

    def test_every_rule_declares_what_it_hides(self, output):
        text = flat(output.stdout)
        assert "race-not-reversal" in text
        assert "stale-copy" in text
        assert "ordered-supersession" in text
        assert "and hides" in text

    def test_it_states_that_a_rule_can_only_subtract(self, output):
        assert "A rule can only subtract." in flat(output.stdout)
        assert "makes the tool find more" in flat(output.stdout)

    def test_it_lists_what_it_removed(self, output):
        assert "removed from the report" in flat(output.stdout)

    def test_it_calls_each_suppression_an_unsettleable_bet(self, output):
        text = flat(output.stdout)
        assert "cannot be settled" in text
        assert "stops learning about the thing it filters" in text


class TestSeverity:
    @pytest.fixture(scope="class")
    def output(self):
        return run("severity", "--relation", "MIRROR")

    def test_it_runs(self, output):
        assert output.exit_code == 0

    def test_it_admits_the_weights_are_invented(self, output):
        text = flat(output.stdout)
        assert "hand-chosen" in text
        assert "the units are nothing" in text

    def test_it_reports_the_score_collision(self, output):
        text = flat(output.stdout)
        assert "not ordinal" in text
        assert "unrelated problems next to each other" in text

    def test_it_separates_severity_from_confidence(self, output):
        assert "two orders and the report shows one" in flat(output.stdout)

    def test_the_ranking_is_labelled_as_an_invented_number(self, output):
        assert "ranked by an invented number" in flat(output.stdout)


class TestReport:
    @pytest.fixture(scope="class")
    def output(self):
        return run("report")

    def test_it_runs(self, output):
        assert output.exit_code == 0

    def test_the_headline_never_gives_a_bare_count(self, output):
        text = flat(output.stdout)
        assert "have a named cause" in text
        assert "UNSEPARABLE" in text

    def test_it_says_what_the_conflict_count_rests_on(self, output):
        assert "rests on the source relation" in flat(output.stdout)

    def test_suppressions_are_not_deducted(self, output):
        assert "not deducted from the totals" in flat(output.stdout)

    def test_it_writes_a_payload_when_asked(self, tmp_path):
        output = run("report", "--relation", "MIRROR", "-o", str(tmp_path))
        assert output.exit_code == 0
        payload = json.loads((tmp_path / "report.json").read_text())
        assert payload["entities"] == 16
        assert payload["relation"] == "MIRROR"
        assert payload["conflicts"] == 3
        assert payload["unseparable"] == 9
        assert payload["idioms_agree"] is False
        assert payload["score_collisions"] == [50]


class TestCompareRelations:
    @pytest.fixture(scope="class")
    def output(self):
        return run("compare-relations")

    def test_it_runs(self, output):
        assert output.exit_code == 0

    def test_it_shows_all_three_declarations(self, output):
        for relation in ("MIRROR", "INDEPENDENT", "UNDECLARED"):
            assert relation in output.stdout

    def test_it_states_that_the_rows_never_changed(self, output):
        text = flat(output.stdout)
        assert "The rows never changed." in text
        assert "not in the data" in text


class TestDoctor:
    @pytest.fixture(scope="class")
    def output(self):
        return run("doctor")

    def test_it_runs(self, output):
        assert output.exit_code == 0

    def test_it_separates_measured_from_invented(self, output):
        text = flat(output.stdout)
        assert "measured from the files" in text
        assert "invented, not measured" in text

    def test_it_says_the_window_was_never_measured(self, output):
        assert "CONFIGURED, never measured" in flat(output.stdout)

    def test_it_lists_four_things_it_cannot_do(self, output):
        text = flat(output.stdout)
        assert "Four things this tool cannot do" in text
        assert "cannot tell silence from dissent" in text
        assert "cannot measure the propagation window" in text
        assert "cannot discover the source relation" in text
        assert "cannot learn from its own suppressions" in text

    def test_it_demonstrates_the_csv_loss_rather_than_asserting_it(self, output):
        text = flat(output.stdout)
        assert "Demonstrated, not asserted" in text
        assert "distinguishable afterwards = False" in text


class TestCheck:
    def test_the_corpus_fails_and_says_why(self):
        output = run("check")
        assert output.exit_code == 1
        text = flat(output.stdout)
        assert "Fixable in the source files" in text
        assert "FAIL on" in text

    def test_it_separates_what_it_will_not_fail_on(self):
        output = run("check")
        text = flat(output.stdout)
        assert "Reported and NOT failed on" in text
        assert "UNSEPARABLE" in text

    def test_it_names_each_fixable_defect(self):
        text = flat(run("check").stdout)
        assert "appear more than once" in text
        assert "naive timestamps in ONE file" in text
        assert "no decision time" in text
        assert "could not be parsed" in text

    def test_clean_files_pass_with_an_unexplained_difference_present(self, tmp_path):
        (tmp_path / "a.csv").write_text(
            "entity,value,decided_at\ne1,APPROVED,2025-03-01T09:00:00\n"
        )
        (tmp_path / "b.csv").write_text(
            "entity,value,decided_at\ne1,REJECTED,2025-03-01T09:00:00\n"
        )
        output = run("check", env={
            "DB_DATA_DIR": str(tmp_path), "DB_LEFT_FILE": "a.csv", "DB_RIGHT_FILE": "b.csv",
        })
        assert output.exit_code == 0
        text = flat(output.stdout)
        assert "Nothing fixable at source" in text
        assert "UNSEPARABLE" in text, "it still reports the difference it cannot explain"

    def test_a_duplicate_key_alone_is_enough_to_fail(self, tmp_path):
        (tmp_path / "a.csv").write_text(
            "entity,value,decided_at\n"
            "e1,APPROVED,2025-03-01T09:00:00\n"
            "e1,REJECTED,2025-03-01T10:00:00\n"
        )
        (tmp_path / "b.csv").write_text(
            "entity,value,decided_at\ne1,APPROVED,2025-03-01T09:00:00\n"
        )
        output = run("check", env={
            "DB_DATA_DIR": str(tmp_path), "DB_LEFT_FILE": "a.csv", "DB_RIGHT_FILE": "b.csv",
        })
        assert output.exit_code == 1
        assert "appear more than once" in flat(output.stdout)


class TestExplain:
    def test_it_walks_the_steps_in_order(self):
        output = run("explain", "e02-ordered-far", "--relation", "MIRROR")
        assert output.exit_code == 0
        text = flat(output.stdout)
        assert "1. pairing" in text
        assert "2. order" in text
        assert "3. influence" in text
        assert "CONFLICT" in text

    def test_a_matching_pair_is_not_a_clean_bill_of_health(self):
        output = run("explain", "e01-agree")
        text = flat(output.stdout)
        assert "nothing to explain" in text
        assert "not a clean bill of health" in text

    def test_a_multiplied_pairing_says_the_row_was_chosen(self):
        text = flat(run("explain", "e10-two-teams").stdout)
        assert "MULTIPLIED" in text
        assert "we chose it" in text

    def test_an_incomparable_pair_explains_the_offset(self):
        text = flat(run("explain", "e05-naive-vs-aware").stdout)
        assert "INCOMPARABLE" in text
        assert "refuses to compare" in text

    def test_a_tie_says_no_sequence_exists(self):
        text = flat(run("explain", "e04-tied").stdout)
        assert "TIED" in text
        assert "no sequence" in text

    def test_a_cache_behind_its_source_is_lag(self):
        text = flat(run("explain", "e11-cache", "--cache", "system-b").stdout)
        assert "STALE" in text
        assert "holds the OLDER decision" in text

    def test_a_cache_ahead_of_its_source_is_not_suppressed(self):
        text = flat(run("explain", "e16-cache-ahead", "--cache", "system-b").stdout)
        assert "UNSEPARABLE" in text
        assert "cannot get ahead of the thing it copies" in text
        assert "not suppressed" in text

    def test_it_names_the_rule_that_would_hide_the_finding(self):
        text = flat(run("explain", "e03-race").stdout)
        assert "RACE" in text
        assert "race-not-reversal would remove this" in text
        assert "It hides:" in text

    def test_it_always_closes_with_where_the_rules_sit(self):
        assert "downstream of the question" in flat(run("explain", "e01-agree").stdout)

    def test_an_entity_missing_from_one_side_says_no_row_at_all(self):
        text = flat(run("explain", "e08-left-only").stdout)
        assert "no row at all" in text
        assert "ONE_SIDED" in text
        assert "not agreement and it is not disagreement" in text

    def test_an_unknown_entity_exits_one(self):
        assert run("explain", "nope").exit_code == 1


class TestEverySettingReachesTheCli:
    def test_the_relation_option_changes_the_answer(self):
        mirror = json.loads(_payload("MIRROR"))
        independent = json.loads(_payload("INDEPENDENT"))
        assert mirror["conflicts"] == 3
        assert independent["conflicts"] == 0
        assert independent["by_cause"]["TRANSITION"] == 3

    def test_the_window_option_moves_races(self, tmp_path):
        wide = run("report", "-o", str(tmp_path), env={"DB_PROPAGATION_MINUTES": "1440"})
        assert wide.exit_code == 0
        payload = json.loads((tmp_path / "report.json").read_text())
        assert payload["by_cause"]["RACE"] > 2, "a wider window turns more differences into races"

    def test_rules_can_be_switched_off(self, tmp_path):
        run("report", "-o", str(tmp_path), env={"DB_APPLY_RULES": "false"})
        payload = json.loads((tmp_path / "report.json").read_text())
        assert payload["suppressed"] == 0
        assert payload["reported"] == payload["differences"]


def _payload(relation: str) -> str:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        run("report", "--relation", relation, "-o", tmp)
        return Path(tmp, "report.json").read_text()
