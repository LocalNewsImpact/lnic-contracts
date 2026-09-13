"""A reviewer's answer has to change what the pipeline does.

"It is a story" used to write one thing -- the link's status back to
`discovered` -- and drop the type. The URL was fetched again, the same
classifier that had misjudged it ran again, and the reviewer's answer was
gone. Somebody who said "opinion" watched the article land in `labeled`
and get enriched, which is the opposite of what they said.

The type is not decoration: `obituary`, `opinion` and `weather` are
statuses no enrichment stage selects, so recording the type IS the
instruction not to enrich.
"""

import pytest

from lnic_contracts import discovery_verdict as verdict


def test_a_verdict_carries_both_halves():
    note = verdict.build(verdict=verdict.IS_A_STORY, kind="opinion")
    assert note["verdict"] == verdict.IS_A_STORY
    assert note["kind"] == "opinion"
    assert note["decided_at"]
    assert verdict.is_readable(note)


def test_a_rejection_must_say_what_it_is_instead():
    """A count of which kind, against a rule or a publisher, is what a fix
    gets built from."""
    with pytest.raises(ValueError, match="kind"):
        verdict.build(verdict=verdict.NOT_A_STORY, kind="  ")


def test_an_ordinary_story_claims_no_category():
    """Most stories are ordinary ones -- news, sport, business, features.

    Making a reviewer choose a category for those means the category is
    invented by the list rather than observed: a sports story stamped
    `news` because the dropdown had to be answered. "It is a story"
    stands alone, and the pipeline classifies it as it would any other.
    """
    note = verdict.build(verdict=verdict.IS_A_STORY)
    assert verdict.is_readable(note), "an ordinary story is a complete answer"
    assert note["kind"] == ""
    assert verdict.status_for(note) is None


def test_the_empty_kind_is_kept_as_a_key():
    """So a reader can tell "no category claimed" from "written by
    something older than this field"."""
    assert "kind" in verdict.build(verdict=verdict.IS_A_STORY)


def test_an_unknown_verdict_is_refused():
    with pytest.raises(ValueError, match="verdict must be"):
        verdict.build(verdict="maybe", kind="news")


@pytest.mark.parametrize("kind", ["obituary", "opinion", "weather"])
def test_a_kept_but_unenriched_type_decides_the_status(kind):
    """These are extracted, keep their category, and are not enriched --
    which the pipeline already does with those statuses. One write says
    both."""
    note = verdict.build(verdict=verdict.IS_A_STORY, kind=kind)
    assert verdict.status_for(note) == kind


@pytest.mark.parametrize("kind", ["news", ""])
def test_an_ordinary_story_leaves_the_status_alone(kind):
    """News IS the ordinary pipeline, and so is an unnamed kind.
    Overriding the status for them would stop articles the corpus wants
    enriched.

    `column` used to be here, on the grounds that a column is ordinary.
    It is not: a column is an opinion type, collected and kept and never
    enriched, and 71 links a reviewer had called columns were on their way
    to being enriched as news."""
    note = verdict.build(verdict=verdict.IS_A_STORY, kind=kind)
    assert verdict.status_for(note) is None


def test_not_a_story_decides_no_status():
    """Nothing is extracted, so there is no article to give a status to.
    The link's own status already excludes it."""
    note = verdict.build(verdict=verdict.NOT_A_STORY, kind="homepage")
    assert verdict.status_for(note) is None


@pytest.mark.parametrize(
    "note",
    [
        None,
        {},
        "opinion",
        {"verdict": "story", "kind": "opinion"},          # no decided_at
        {"kind": "opinion", "decided_at": "2026-09-09"},  # no verdict
        # A rejection with no kind: the one shape where kind is required.
        {"verdict": "not_story", "decided_at": "2026-09-09"},
        {"verdict": "not_story", "kind": None, "decided_at": "2026-09-09"},
    ],
)
def test_an_unusable_verdict_is_not_acted_on(note):
    """A None value is the one that nearly got through: `str(None)` is
    "None", which is not empty, so a naive truthiness check called it
    readable."""
    assert not verdict.is_readable(note)
    assert verdict.status_for(note) is None
    with pytest.raises(verdict.UnreadableVerdict):
        verdict.read(note)


def test_who_decided_is_optional_and_kept():
    """Useful in an audit trail, never required to act on -- a verdict
    that cannot be acted on because nobody recorded a username would be a
    worse failure than an anonymous one."""
    note = verdict.build(
        verdict=verdict.IS_A_STORY, kind="obituary", decided_by="ed"
    )
    assert note["decided_by"] == "ed"
    assert verdict.is_readable(verdict.build(verdict=verdict.IS_A_STORY, kind="obituary"))


# ------------------------------------------- wire is never fetched at all


def test_wire_keeps_the_link_out_of_the_fetch_queue():
    """A reviewer who reads a URL and says "wire" has already reached the
    conclusion a fetch, an extraction and a wire check would reach. The
    kind was recorded and then ignored, so the pipeline did all three
    anyway."""
    note = verdict.build(verdict=verdict.IS_A_STORY, kind="wire")
    assert verdict.link_status_for(note) == "wire"
    assert verdict.link_status_for(note) != verdict.VERIFIED_STATUS


def test_an_ordinary_story_is_verified_not_sent_back_to_verification():
    """The discovery queue is a POST-verification review. StorySniffer has
    already run -- that is how the link got a status -- and a reviewer is
    approving, rejecting or correcting what it decided. That places the
    record after verification, so its status is verification's OUTPUT
    (`article`), never its input (`discovered`).

    It used to be `discovered` -- verification's INPUT -- so the verdict
    went back to StorySniffer to be guessed at again. 449 human verdicts
    were sitting there, unable to move at all with the verification cron
    suspended.

    The general rule, and the reason this is in the contract: a review
    that happens after a stage is an approval, a rejection, or a change to
    that stage's output. It does not put the record back into the stage it
    has just been reviewed out of."""
    for kind in ("", "column", "opinion", "obituary", "weather"):
        note = verdict.build(
            verdict=verdict.IS_A_STORY, kind=kind
        )
        assert verdict.link_status_for(note) == verdict.VERIFIED_STATUS, kind
        assert verdict.link_status_for(note) == "article", kind
        assert verdict.link_status_for(note) != "discovered", kind


def test_unfetched_and_unenriched_are_different_instructions():
    """Unenriched types are extracted and kept and merely not enriched.
    Unfetched types are never fetched, so no article row exists. Conflating
    them would either enrich wire or throw away obituaries."""
    assert not set(verdict.UNFETCHED_TYPES) & set(
        verdict.UNENRICHED_TYPES
    )
    # And each function answers only its own question.
    wire = verdict.build(
        verdict=verdict.IS_A_STORY, kind="wire"
    )
    assert verdict.status_for(wire) is None, (
        "wire has no article status: there is no article"
    )
    obituary = verdict.build(
        verdict=verdict.IS_A_STORY, kind="obituary"
    )
    assert verdict.status_for(obituary) == "obituary"
    assert (
        verdict.link_status_for(obituary)
        == verdict.VERIFIED_STATUS
    )


def test_an_unusable_verdict_restores_rather_than_raising():
    """A caller in the middle of writing one row can do nothing useful
    with an exception here."""
    for bad in (None, {}, {"verdict": "story"}, {"verdict": "not_story"}, "nonsense"):
        assert (
            verdict.link_status_for(bad) == verdict.VERIFIED_STATUS
        ), bad


def test_a_human_verdict_never_returns_a_stage_input():
    """The general rule, held as a test. `discovered` is verification's
    input; a verdict that resolves to it sends a reviewed record back to
    be judged by the process the reviewer was correcting."""
    for kind in ("", "news", "column", "opinion", "obituary", "weather", "wire"):
        note = verdict.build(verdict=verdict.IS_A_STORY, kind=kind)
        assert verdict.link_status_for(note) != "discovered", kind
    for bad in (None, {}, {"verdict": "story"}, "nonsense"):
        assert verdict.link_status_for(bad) != "discovered", bad


# --- a column is opinion, and `other` is not an article --------------------------


def test_a_column_is_collected_and_never_enriched():
    """A column is an opinion type: local content the corpus collects and
    keeps, which receives neither CIN coding nor enrichment. It was
    described in this module as "the ordinary pipeline", so 71 links a
    reviewer had called columns were on their way to being enriched as
    news."""
    note = verdict.build(verdict=verdict.IS_A_STORY, kind="column")
    assert verdict.link_status_for(note) == "article", "it is still collected"
    assert verdict.status_for(note) == "opinion", "and never enriched"
    assert "column" in verdict.UNENRICHED_TYPES


def test_a_column_lands_in_a_status_the_pipeline_already_has():
    """`column` is not a pipeline status. Writing one would leave articles
    in a status no stage selects and no report counts. A column IS an
    opinion type, so it lands where opinion lands, and the kind stays in
    the verdict for anyone who needs the finer distinction."""
    note = verdict.build(verdict=verdict.IS_A_STORY, kind="column")
    assert verdict.status_for(note) != "column"
    assert note["kind"] == "column", "the distinction is not lost"


def test_other_is_not_an_article_and_is_never_fetched():
    """A reviewer reaching for `other` has found something that is not an
    article. It used to resolve to `article` -- verification's output --
    which sent a non-article to be fetched."""
    note = verdict.build(verdict=verdict.IS_A_STORY, kind="other")
    assert verdict.link_status_for(note) == "not_article"
    assert verdict.link_status_for(note) != "article"
    assert verdict.status_for(note) is None, "no article is created for it"
    assert "other" in verdict.UNFETCHED_TYPES


def test_news_is_the_only_ordinary_story():
    """Everything else a reviewer can name constrains what happens next.
    `news`, and an unnamed kind, are the pipeline's to decide."""
    for kind in ("news", ""):
        note = verdict.build(verdict=verdict.IS_A_STORY, kind=kind)
        assert verdict.status_for(note) is None, kind
        assert verdict.link_status_for(note) == "article", kind


def test_every_named_kind_resolves_to_a_status_that_exists():
    """A kind mapping to a status nothing selects is a record stranded
    silently. These are the statuses the pipeline actually carries --
    docs/PIPELINE_STATES.md in the crawler."""
    link_statuses = {"article", "wire", "not_article", "discovered"}
    article_statuses = {"obituary", "opinion", "weather", None}
    for kind in ("news", "column", "other", "obituary", "opinion", "weather", "wire"):
        note = verdict.build(verdict=verdict.IS_A_STORY, kind=kind)
        assert verdict.link_status_for(note) in link_statuses, kind
        assert verdict.status_for(note) in article_statuses, kind


def test_the_two_sets_still_mean_different_things():
    """Unfetched is stronger than unenriched, and no kind is both: one
    would be fetched and not fetched."""
    assert not set(verdict.UNFETCHED_TYPES) & set(verdict.UNENRICHED_TYPES)
    for kind in verdict.UNFETCHED_TYPES:
        assert kind in verdict.UNFETCHED_STATUS, kind
