"""A row nobody can select is a row nobody closes.

`pipeline_rework` is written by the datadesk console and read by the
crawler. The pairing of stage to status is what makes a row work: a row
written against the wrong status is accepted by the database, selected by
no stage, and left open forever -- so the nightly guard reports work
owed, every stage runs, and nothing happens. Neither repository's tests
could see that, because each held its own copy of the names.

These pin the pairing, and the refusals that catch a row before it exists.
"""

import pytest

from lnic_contracts import pipeline_rework as rework


def test_the_stages_are_the_ones_housekeeping_runs():
    """Discovery and URL verification are absent deliberately: they are
    the pipeline's own crons, and housekeeping starts at records ready
    for extraction. A restored link goes to `discovered`, which is
    verification's input -- a row for it would never be closed."""
    assert rework.STAGES == ("extract", "classify", "enrich")
    assert "discover" not in rework.STAGES
    assert "verify" not in rework.STAGES


def test_extraction_works_on_a_link_and_the_rest_on_articles():
    """Extraction selects `candidate_links.status`, so an article sent
    back for a fetch has to reach its LINK. Setting an article's status
    to `article` schedules nothing at all, and an earlier draft of the
    reconciler did exactly that."""
    assert rework.record_type_for("extract") == "candidate_link"
    assert rework.record_type_for("classify") == "article"
    assert rework.record_type_for("enrich") == "article"


def test_each_stage_selects_the_status_the_pipeline_gives_it():
    assert rework.selects("extract") == ("article",)
    assert rework.selects("enrich") == ("labeled",)


def test_classification_takes_local_as_well_as_cleaned():
    """`analyze` defaults to `['cleaned', 'local']`. Leaving `local` out
    here would refuse a row for an article the wire check has cleared,
    which is most of them."""
    assert rework.selects("classify") == ("cleaned", "local")


def test_the_chain_runs_forward_and_stops():
    """Each stage queues the one after it, because the console cannot:
    extraction's article does not exist until the fetch, so nothing
    upstream knows its id. Enrichment queues nothing -- a stage after it
    would loop."""
    assert rework.next_stage("extract") == "classify"
    assert rework.next_stage("classify") == "enrich"
    assert rework.next_stage("enrich") is None


def test_the_end_of_the_chain_is_what_the_export_selects():
    """Carrying a record is only finished when it is in the export."""
    assert rework.PUBLISHED == ("enriched", "enrichment_skipped")
    assert rework.next_stage(rework.STAGES[-1]) is None


# --- what `check` refuses ---------------------------------------------------------


def test_a_row_a_stage_can_select_is_allowed():
    rework.check(stage="classify", record_type="article", status="cleaned")
    rework.check(stage="extract", record_type="candidate_link", status="article")
    rework.check(stage="enrich", record_type="article", status="labeled")


def test_the_wrong_record_type_is_refused():
    with pytest.raises(ValueError, match="works on a candidate_link"):
        rework.check(stage="extract", record_type="article", status="article")


def test_the_wrong_status_is_refused():
    """The silent failure, caught at the only moment it is detectable."""
    with pytest.raises(ValueError, match="selects"):
        rework.check(stage="enrich", record_type="article", status="cleaned")


def test_a_stage_nothing_runs_is_refused_by_name():
    """The message has to say why, or the next person adds the stage
    instead of the cron."""
    with pytest.raises(ValueError, match="not a housekeeping stage"):
        rework.check(stage="verify", record_type="candidate_link", status="discovered")
    with pytest.raises(ValueError, match="nobody will ever close"):
        rework.next_stage("fetch_with_browser")


def test_every_accessor_refuses_an_unknown_stage():
    """One refusal per entry point; a caller reaching any of them with a
    typo gets the same answer."""
    for call in (
        rework.record_type_for,
        rework.selects,
        rework.next_stage,
    ):
        with pytest.raises(ValueError):
            call("classifyy")


# --- the shape both repositories depend on ---------------------------------------


def test_the_table_is_named_here():
    """The console writes to it by name and does not own its schema."""
    assert rework.TABLE == "pipeline_rework"


def test_the_mapping_and_the_stage_list_cannot_drift_apart():
    """A stage added to one and not the other is a stage with no statuses
    or statuses with no stage."""
    assert tuple(rework.SELECTS) == rework.STAGES
    assert tuple(rework.FOLLOWS) == rework.STAGES


def test_every_record_type_used_is_declared():
    declared = set(rework.RECORD_TYPES)
    assert {t for t, _ in rework.SELECTS.values()} <= declared


def test_the_chain_is_a_line_not_a_cycle():
    """Following it from the first stage reaches the end, visiting each
    stage once. A cycle would carry a record forever."""
    seen = []
    stage = rework.STAGES[0]
    while stage is not None:
        assert stage not in seen, f"{stage} revisited"
        seen.append(stage)
        stage = rework.next_stage(stage)
    assert seen == list(rework.STAGES)
