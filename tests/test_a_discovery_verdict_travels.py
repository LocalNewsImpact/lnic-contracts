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


def test_the_kind_is_required():
    """Without it a restored URL is re-classified by the model that got it
    wrong, which is the fault this exists to fix."""
    with pytest.raises(ValueError, match="kind"):
        verdict.build(verdict=verdict.IS_A_STORY, kind="  ")


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


@pytest.mark.parametrize("kind", ["news", "column"])
def test_an_ordinary_story_leaves_the_status_alone(kind):
    """News and columns ARE the ordinary pipeline. Overriding the status
    for them would stop articles the corpus wants enriched."""
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
        {"verdict": "story"},
        {"verdict": "story", "kind": "opinion"},
        {"verdict": "story", "kind": None, "decided_at": "2026-09-09"},
        {"verdict": "story", "kind": "   ", "decided_at": "2026-09-09"},
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
