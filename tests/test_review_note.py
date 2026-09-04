"""The note that lets a held article be released.

Both repositories had a test asserting these four keys, and neither test
could see the other. A key renamed on one side was invisible until an
article was held and could not be let out -- stranded, out of the pipeline,
with the status it was held from gone.

These tests are the ones neither side could write alone.
"""

from datetime import UTC, datetime

import pytest

from lnic_contracts import review_note as rn


def _note(**overrides):
    note = rn.build(
        claim="byline_not_a_name", status_before="labeled", stage="extraction"
    )
    note.update(overrides)
    return note


# --- the shape ----------------------------------------------------------------


def test_a_built_note_carries_exactly_the_required_keys():
    assert set(_note()) == set(rn.REQUIRED_KEYS)


def test_a_built_note_is_readable():
    assert rn.is_readable(_note())


@pytest.mark.parametrize("key", rn.REQUIRED_KEYS)
def test_every_key_is_required(key):
    """One test per key. A key quietly dropped fails here rather than on a
    held article that cannot be released."""
    note = {k: v for k, v in _note().items() if k != key}
    assert rn.missing_keys(note) == [key]
    assert not rn.is_readable(note)


def test_a_renamed_key_is_caught():
    """The failure this package exists to prevent."""
    note = _note()
    note["prior_status"] = note.pop("status_before")
    assert "status_before" in rn.missing_keys(note)


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_an_empty_value_is_as_bad_as_a_missing_key(empty):
    """Neither can restore an article or name a question."""
    assert "claim" in rn.missing_keys(_note(claim=empty))


def test_something_that_is_not_a_note_at_all():
    for value in (None, "", [], "a string", 7):
        assert rn.missing_keys(value) == list(rn.REQUIRED_KEYS)


# --- building it --------------------------------------------------------------


def test_the_status_must_be_read_before_the_hold_is_applied():
    """The defect this guards, which shipped once: `status` was read after
    being overwritten, so the note recorded `in_review` as the status to
    restore and the article could never be put back."""
    with pytest.raises(ValueError, match="read it before"):
        rn.build(claim="c", status_before=rn.IN_REVIEW, stage="extraction")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"claim": "", "status_before": "labeled", "stage": "extraction"},
        {"claim": "c", "status_before": "", "stage": "extraction"},
        {"claim": "c", "status_before": "labeled", "stage": ""},
    ],
)
def test_a_hold_without_all_three_facts_is_refused(kwargs):
    with pytest.raises(ValueError):
        rn.build(**kwargs)


def test_a_supplied_timestamp_is_used():
    when = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    assert rn.build(
        claim="c", status_before="labeled", stage="s", held_at=when
    )["held_at"] == when.isoformat()


# --- reading it ---------------------------------------------------------------


def test_read_raises_naming_what_is_wrong():
    note = {k: v for k, v in _note().items() if k != "status_before"}
    with pytest.raises(rn.UnreadableNote, match="status_before"):
        rn.read(note)


def test_read_returns_a_copy():
    note = _note()
    rn.read(note)["claim"] = "changed"
    assert note["claim"] == "byline_not_a_name"


# --- in and out of metadata ----------------------------------------------------


def test_a_note_survives_the_round_trip_through_metadata():
    meta = rn.into_metadata({"extraction_method": "trafilatura"}, _note())
    assert rn.is_readable(rn.from_metadata(meta))
    assert meta["extraction_method"] == "trafilatura"


def test_metadata_that_arrived_as_json_text_is_read():
    """The two services reach the column through different layers."""
    import json

    assert rn.is_readable(rn.from_metadata(json.dumps({"review": _note()})))


def test_metadata_with_no_note_reads_as_empty_not_an_error():
    for value in (None, {}, "{}", "not json", 7, {"review": "not a dict"}):
        assert rn.from_metadata(value) == {}


def test_an_existing_note_is_never_overwritten():
    """Re-holding would replace the status the article was FIRST held from,
    which is the one thing that can put it back."""
    first = rn.into_metadata({}, _note(claim="first"))
    second = rn.into_metadata(first, _note(claim="second"))
    assert second["review"]["claim"] == "first"


def test_the_held_status_is_not_one_the_pipeline_reads():
    """Labeling reads cleaned/local, enrichment reads labeled. If
    IN_REVIEW ever became one of those, holding would stop holding."""
    assert rn.IN_REVIEW not in ("cleaned", "local", "labeled", "extracted")


# --- a decision the crawler can see ------------------------------------------
#
# A decision recorded only in the console does not reach the pipeline: the
# crawler raises a hold from the article's own fields, so a claim somebody
# answered is raised again the next time those fields are read, and the
# same question returns to the queue.


def test_a_decision_carries_what_the_crawler_needs():
    decision = rn.build_decision(
        claim="byline_not_a_name", stage="extraction", decision="accept"
    )
    for key in rn.DECISION_KEYS:
        assert decision.get(key), f"a decision without {key} cannot be read back"


def test_a_decision_must_say_what_it_answered():
    for missing in ("claim", "stage", "decision"):
        kwargs = {"claim": "c", "stage": "s", "decision": "accept"}
        kwargs[missing] = ""
        with pytest.raises(ValueError):
            rn.build_decision(**kwargs)


def test_an_answered_claim_reads_as_answered():
    meta = rn.record_decision(
        {},
        rn.build_decision(
            claim="byline_not_a_name", stage="extraction", decision="accept"
        ),
    )
    assert rn.is_answered(meta, claim="byline_not_a_name", stage="extraction")


def test_the_same_claim_from_another_stage_is_unanswered():
    """The question is the claim AND the stage that raised it."""
    meta = rn.record_decision(
        {},
        rn.build_decision(
            claim="byline_not_a_name", stage="extraction", decision="accept"
        ),
    )
    assert not rn.is_answered(
        meta, claim="byline_not_a_name", stage="labeling"
    )


def test_a_decision_survives_a_later_hold():
    """The hold note is dropped and rewritten every time a fresh hold is
    applied. A decision stored inside it would be erased by the next hold,
    which is the loop this exists to break."""
    meta = rn.record_decision(
        {},
        rn.build_decision(claim="text_not_decoded", stage="extraction", decision="accept"),
    )
    meta.pop(rn.METADATA_KEY, None)
    meta = rn.into_metadata(
        meta,
        rn.build(claim="byline_not_a_name", status_before="labeled", stage="extraction"),
    )
    assert rn.is_answered(meta, claim="text_not_decoded", stage="extraction")
    assert rn.is_readable(rn.from_metadata(meta))


def test_revisiting_a_question_replaces_the_answer():
    """Unlike the hold note, which refuses to overwrite: a person may
    revisit a question, and the newest answer is the one that holds."""
    meta = rn.record_decision(
        {},
        rn.build_decision(claim="c", stage="extraction", decision="accept"),
    )
    meta = rn.record_decision(
        meta,
        rn.build_decision(claim="c", stage="extraction", decision="reject"),
    )
    recorded = rn.decision_for(meta, claim="c", stage="extraction")
    assert recorded["decision"] == "reject"
    assert len(rn.decisions(meta)) == 1


def test_an_incomplete_decision_is_refused():
    with pytest.raises(rn.UnreadableNote):
        rn.record_decision({}, {"claim": "c", "stage": "extraction"})


def test_metadata_that_is_not_a_mapping_answers_nothing():
    for value in (None, "", "review", 7, []):
        assert rn.decisions(value) == {}
        assert not rn.is_answered(value, claim="c", stage="extraction")


def test_the_question_key_is_defined_once():
    """Both repositories have to produce the same string. Two
    implementations of "the same question" is the defect this package
    exists to prevent."""
    assert rn.question("byline_not_a_name", "extraction") == (
        "byline_not_a_name:extraction"
    )
