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
    Unfetched types are never fetched. Conflating them would either enrich
    wire or throw away obituaries.

    "Never fetched" is a rule about the LINK. It was read as "so no article
    row exists", and that is false of the record: articles exist for all of
    these -- extracted before the verdict was given, or given a verdict
    afterwards. `status_for` answering None for them parked the article at
    `labeled`, refused by enrichment and unreachable by any settle."""
    assert not set(verdict.UNFETCHED_TYPES) & set(
        verdict.UNENRICHED_TYPES
    )
    wire = verdict.build(
        verdict=verdict.IS_A_STORY, kind="wire"
    )
    assert verdict.status_for(wire) == "wire", (
        "a reviewer calling something wire means it is wire"
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
    # And where an article already exists for one, it is a non-article too:
    # the same answer on both sides, rather than a row parked at `labeled`.
    assert verdict.status_for(note) == "not_article"
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
    link_statuses = {"article", "wire", "not_article", "discovered", "non_english"}
    article_statuses = {
        "obituary",
        "opinion",
        "weather",
        "wire",
        "non_english",
        "not_article",
        None,
    }
    for kind in (
        "news",
        "column",
        "other",
        "obituary",
        "opinion",
        "weather",
        "wire",
        "non_english",
    ):
        note = verdict.build(verdict=verdict.IS_A_STORY, kind=kind)
        assert verdict.link_status_for(note) in link_statuses, kind
        assert verdict.status_for(note) in article_statuses, kind


def test_the_two_sets_still_mean_different_things():
    """Unfetched is stronger than unenriched, and no kind is both: one
    would be fetched and not fetched."""
    assert not set(verdict.UNFETCHED_TYPES) & set(verdict.UNENRICHED_TYPES)
    for kind in verdict.UNFETCHED_TYPES:
        assert kind in verdict.UNFETCHED_STATUS, kind


# --- a non-English story is kept, not fetched, and countable ---------------------


def test_a_non_english_story_is_not_fetched():
    """It IS a story, and the pipeline cannot read it: the classifier, the
    CIN codebook and the enrichment prompts are all written for English, so
    a fetch spends a request and model budget to produce labels nobody
    should trust. A reviewer who can see the language from the URL has
    answered more cheaply and more reliably."""
    note = verdict.build(verdict=verdict.IS_A_STORY, kind="non_english")
    assert "non_english" in verdict.UNFETCHED_TYPES
    assert verdict.link_status_for(note) != "article", "never sent to be fetched"
    # Where one was fetched before the verdict arrived, the article says so
    # too, instead of sitting at `labeled` where nothing can reach it.
    assert verdict.status_for(note) == "non_english"


def test_it_keeps_a_status_of_its_own_so_it_stays_countable():
    """The reason it is not folded into an existing status. Inside
    `not_article` it is indistinguishable from a section front; inside
    `wire` it is indistinguishable from syndication. Either way "how much of
    what these publishers write is not in English" stops being answerable,
    and that is a finding about local news coverage rather than a processing
    detail."""
    note = verdict.build(verdict=verdict.IS_A_STORY, kind="non_english")
    assert verdict.link_status_for(note) == "non_english"
    assert verdict.link_status_for(note) not in ("not_article", "wire")


def test_every_unfetched_kind_has_its_own_declared_status():
    """A kind in the set with no status resolves to None and the link is
    written with nothing."""
    for kind in verdict.UNFETCHED_TYPES:
        assert kind in verdict.UNFETCHED_STATUS, kind
        assert verdict.UNFETCHED_STATUS[kind], kind


def test_a_non_english_verdict_is_still_a_story_verdict():
    """The reviewer said it IS a story. That must survive in the note, or
    the count becomes "not a story, language unknown"."""
    note = verdict.build(verdict=verdict.IS_A_STORY, kind="non_english")
    assert note["verdict"] == verdict.IS_A_STORY
    assert note["kind"] == "non_english"


# ---------------------------------------------------------------------------
# A section front is not a story, and it is the one kind the crawler decides
# by itself -- from the URL shape, before any person sees it.
# ---------------------------------------------------------------------------


class TestASectionFrontIsCountable:
    def test_it_has_a_status_of_its_own(self):
        """Folded into `not_article` the question "how many of these did
        discovery queue as stories" stops being answerable. That is the
        same argument the `non_english` comment makes from the other
        direction, naming the section front as the thing it must not be
        confused with."""
        assert verdict.SECTION_FRONT == "section_front"
        assert verdict.SECTION_FRONT not in ("not_article", "wire")

    def test_the_kind_and_the_status_are_different_names(self):
        """The console's list says `section_index`; the status says
        `section_front`. Both names already exist in their own repository,
        so the contract holds the mapping rather than asking one side to
        rename and break a queue or a query."""
        assert verdict.SECTION_FRONT_KIND == "section_index"
        assert (
            verdict.NOT_STORY_STATUS[verdict.SECTION_FRONT_KIND]
            == verdict.SECTION_FRONT
        )

    def test_it_is_never_fetched_and_never_classified(self):
        """There is no story on the page. An article row for one holds
        navigation as its body, which is what the 104 in production do."""
        assert verdict.SECTION_FRONT in verdict.NEVER_FETCHED
        assert verdict.SECTION_FRONT in verdict.NEVER_CLASSIFIED

    def test_the_never_lists_still_contain_everything_they_did(self):
        """Added to, not replaced. A list that quietly stopped covering
        `wire` or `obituary` would reopen every bug those entries close."""
        for kind in verdict.UNFETCHED_TYPES:
            assert kind in verdict.NEVER_FETCHED, kind
        for kind in verdict.UNENRICHED_TYPES:
            assert kind in verdict.NEVER_CLASSIFIED, kind


class TestARejectionIsNotAVerification:
    def _note(self, kind):
        return {
            "verdict": verdict.NOT_A_STORY,
            "kind": kind,
            "decided_at": "2026-09-13T00:00:00+00:00",
        }

    def test_a_rejected_section_front_holds_its_own_status(self):
        assert (
            verdict.link_status_for(self._note("section_index"))
            == verdict.SECTION_FRONT
        )

    def test_every_other_rejection_lands_in_not_article(self):
        for kind in ("homepage", "search", "feed", "tag_or_author", "video"):
            assert (
                verdict.link_status_for(self._note(kind)) == "not_article"
            ), kind

    def test_a_rejection_is_never_sent_to_be_fetched(self):
        """THE POINT. This branch used to return VERIFIED_STATUS, which
        queues a fetch -- for a URL a person had just said was not a
        story. The console never reaches it, so nothing was fetched on
        this path in production, but it was the wrong answer waiting for
        the next caller."""
        for kind in ("section_index", "homepage", "search", "video", "file"):
            got = verdict.link_status_for(self._note(kind))
            assert got != verdict.VERIFIED_STATUS, kind

    def test_a_rejection_with_no_kind_is_malformed_and_fails_safe(self):
        """`kind` is required for `not_story` -- KIND_REQUIRED_FOR says so --
        so a rejection without one is not a readable verdict at all. It
        keeps the old fallback rather than withholding a URL on the
        strength of a half-written note."""
        assert (
            verdict.link_status_for(self._note("")) == verdict.VERIFIED_STATUS
        )

    def test_a_story_verdict_is_untouched_by_any_of_this(self):
        decided = "2026-09-13T00:00:00+00:00"
        story = {"verdict": verdict.IS_A_STORY, "decided_at": decided}
        assert (
            verdict.link_status_for({**story, "kind": "news"})
            == verdict.VERIFIED_STATUS
        )
        assert (
            verdict.link_status_for({**story, "kind": ""})
            == verdict.VERIFIED_STATUS
        )
        assert verdict.link_status_for({**story, "kind": "wire"}) == "wire"
        assert (
            verdict.link_status_for({**story, "kind": "non_english"})
            == "non_english"
        )

    def test_an_unreadable_note_still_fails_safe(self):
        """A malformed verdict cannot be read as a rejection either, so it
        keeps the old fallback rather than silently withholding a URL."""
        assert (
            verdict.link_status_for({})
            == verdict.VERIFIED_STATUS
        )
        assert (
            verdict.link_status_for(None)
            == verdict.VERIFIED_STATUS
        )


# ---------------------------------------------------------------------------
# An article that already exists, and a verdict that arrives for it.
# ---------------------------------------------------------------------------


class TestAVerdictDecidesAnArticleThatAlreadyExists:
    def _story(self, kind):
        return {
            "verdict": verdict.IS_A_STORY,
            "kind": kind,
            "decided_at": "2026-09-13T00:00:00+00:00",
        }

    def test_a_reviewer_calling_it_wire_makes_it_wire(self):
        """A reviewer calling something wire means it is wire. The queue
        exists so a person's answer decides; weighing it against the
        detector's evidence afterwards is the failure the queue was built
        to end.

        This answered None, so three articles sat at `labeled` -- refused
        by enrichment, unreachable by any settle, outstanding for ever --
        and had to be moved by hand."""
        assert verdict.status_for(self._story("wire")) == "wire"

    def test_every_unfetched_kind_answers_now(self):
        for kind in verdict.UNFETCHED_TYPES:
            assert verdict.status_for(self._story(kind)) is not None, kind

    def test_every_withheld_kind_lands_somewhere_terminal(self):
        """The point is reachability. A status that no stage selects and no
        settle can close is worse than a wrong one: it is invisible."""
        parked = {"labeled", "cleaned", "local", "extracted", "discovered"}
        for kind in verdict.UNENRICHED_TYPES + verdict.UNFETCHED_TYPES:
            got = verdict.status_for(self._story(kind))
            assert got is not None, kind
            assert got not in parked, f"{kind} -> {got} is not terminal"

    def test_the_unenriched_kinds_answer_exactly_what_they_did(self):
        """Added to, not changed. These four already worked and a
        regression here would re-enrich obituaries."""
        assert verdict.status_for(self._story("obituary")) == "obituary"
        assert verdict.status_for(self._story("opinion")) == "opinion"
        assert verdict.status_for(self._story("weather")) == "weather"
        assert verdict.status_for(self._story("column")) == "opinion"

    def test_a_column_still_lands_in_opinion_not_in_a_status_of_its_own(self):
        """`column` is not a pipeline status. Inventing one would leave a
        status nothing selects and nothing reports."""
        assert verdict.status_for(self._story("column")) == "opinion"
        assert "column" not in verdict.WITHHELD_STATUS.values()

    def test_an_ordinary_story_still_decides_nothing(self):
        """The commonest verdict. The pipeline classifies it as it would
        any other, which is the whole point of not making somebody choose a
        category."""
        assert verdict.status_for(self._story("news")) is None
        assert verdict.status_for(self._story("")) is None

    def test_a_rejection_decides_no_article_status(self):
        """`status_for` answers what an ARTICLE should be. A rejection is
        answered by `link_status_for`, which is a different question."""
        assert (
            verdict.status_for(
                {
                    "verdict": verdict.NOT_A_STORY,
                    "kind": "section_index",
                    "decided_at": "2026-09-13T00:00:00+00:00",
                }
            )
            is None
        )

    def test_an_unreadable_note_decides_nothing(self):
        assert verdict.status_for({}) is None
        assert verdict.status_for(None) is None

    def test_withheld_status_covers_both_families_and_nothing_else(self):
        """So a kind added to either tuple is answered here without this
        mapping being edited, and a kind in neither is never withheld."""
        assert set(verdict.WITHHELD_STATUS) == set(
            verdict.UNENRICHED_TYPES + verdict.UNFETCHED_TYPES
        )
        assert "news" not in verdict.WITHHELD_STATUS
