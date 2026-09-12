"""A person has judged a URL; the pipeline has to act on the judgement.

WHAT THIS IS FOR
----------------
The discovery review queue asks one question before anything is fetched:
is this URL a story, and what kind. Both halves matter to what happens
next, and only one of them used to survive the answer.

"It is a story" set `candidate_links.status` back to `discovered`, so the
URL was fetched again -- and then the pipeline re-ran the same classifier
that had misjudged it badly enough to put it in the queue, reached its
own conclusion, and the reviewer's was gone. A reviewer who said
"opinion" watched the article land in `labeled` and get enriched, which
is the opposite of what they said.

The type is not decoration. `obituary`, `opinion` and `weather` are real
pipeline statuses selected by no enrichment stage, so recording the type
IS the instruction not to enrich. One write carries both.

WHY IT IS SHARED CODE AND NOT A CONVENTION
------------------------------------------
The console writes the verdict. The crawler reads it after extraction and
sets the article's status from it. This is the same split, and the same
hazard, as `review_note`: two repositories each holding their own copy of
the key names, and a rename on one side invisible until a reviewer's
decision quietly stopped changing anything.

One definition, imported by both. Renaming a key here breaks the build of
every consumer, which is the conversation a silent rename skipped.

WHERE IT LIVES
--------------
`candidate_links.meta` under `review_verdict`. On the link and not on the
article, because at the moment it is written there is no article -- that
is the whole point of the queue.
"""

from __future__ import annotations

from datetime import UTC, datetime

#: Where the verdict lives inside `candidate_links.meta`.
METADATA_KEY = "review_verdict"

#: What a reviewer can have said about the URL itself.
IS_A_STORY = "story"
NOT_A_STORY = "not_story"
VERDICTS: tuple[str, ...] = (IS_A_STORY, NOT_A_STORY)

#: The status a human story verdict puts a link in: VERIFIED, and waiting
#: to be fetched.
#:
#: This was `discovered` -- verification's INPUT -- so a person who read a
#: URL and said "this is a story" sent it back to StorySniffer to be
#: guessed at again. 449 human verdicts sat there, and with the
#: verification cron suspended they could not move at all.
#:
#: Nothing is skipped and nothing is repeated. This review is
#: POST-verification: StorySniffer has already run -- that is how the link
#: got a status at all -- and the discovery queue shows what it decided.
#: A reviewer there is approving, rejecting or correcting a verification
#: that has already happened, which places the record AFTER verification,
#: whichever way the answer goes.
#:
#: So the status is verification's OUTPUT. `article` when the answer is
#: "it is a story", the kind itself when the answer keeps it out of the
#: fetch queue. Never `discovered`, which is verification's INPUT: that
#: returns the record to the process whose answer was just reviewed, to be
#: decided again by the thing that got it wrong.
#:
#: The general rule, which is why this lives in the contract rather than
#: in one queue: a review after a stage is an approval, a rejection, or a
#: change to that stage's output, and the record carries on from there.
#:
#: The exception is a reviewer explicitly asking for a stage to be redone
#: -- `reextract` in the extraction queue -- where going back is the
#: instruction rather than an accident of the mapping.
VERIFIED_STATUS = "article"

#: Types that are stories and are extracted, but which no enrichment
#: stage selects. A verdict naming one of these is the instruction to
#: keep the article and stop before enrichment -- there is no separate
#: flag, because the status already means it.
#:
#: `news` and `column` are absent deliberately: those ARE the ordinary
#: pipeline, and an article of that kind should be enriched like any
#: other. A type here is a story the corpus keeps and does not spend
#: model budget on.
UNENRICHED_TYPES: tuple[str, ...] = ("obituary", "opinion", "weather")

#: Types that are stories and should never be fetched at all.
#:
#: Wire is syndicated: the same article runs at a dozen papers, the
#: corpus keeps it out of BigQuery, and nothing downstream reads a wire
#: body. Fetching one spends a request, an extraction and a wire check to
#: reach a conclusion a reviewer already reached by reading the URL.
#:
#: This is a stronger instruction than UNENRICHED_TYPES. Those are
#: extracted and kept and merely not enriched; these are not fetched, so
#: no article row is ever created. A reviewer marking wire in the
#: discovery queue was previously restoring the link to `discovered` --
#: the fetch queue -- and the kind was recorded and then ignored, so the
#: pipeline fetched it, extracted it, and rediscovered by itself what the
#: person had already said.
UNFETCHED_TYPES: tuple[str, ...] = ("wire",)

#: What the verdict must carry, and why each one:
#:
#: verdict   story or not_story. What the reviewer answered.
#: kind      what kind of story, or what it is instead.
#: decided_at  when. A verdict older than the last re-verification is a
#:           verdict about a different answer.
REQUIRED_KEYS: tuple[str, ...] = ("verdict", "decided_at")

#: `kind` is required for `not_story` and optional for `story`.
#:
#: A URL rejected as "not a story" is worth naming -- section front, tag
#: page, homepage -- because a count of which kind, against a rule or a
#: publisher, is what a fix gets built from.
#:
#: A story is different. Most stories are ordinary ones: news, sport,
#: business, features. Making a reviewer choose a category for those
#: means the category is invented by the list rather than observed --
#: a sports story stamped `news` because the dropdown had to be
#: answered. An empty kind says "an ordinary story", the pipeline
#: classifies it as it would any other, and nothing is claimed that
#: nobody saw.
KIND_REQUIRED_FOR: tuple[str, ...] = (NOT_A_STORY,)


class UnreadableVerdict(ValueError):
    """A verdict the pipeline cannot act on."""


def build(
    *, verdict: str, kind: str = "", decided_at=None, decided_by: str = ""
) -> dict:
    """The verdict to write when a reviewer answers a discovery row.

    `kind` is optional for a story and required for a rejection. See
    KIND_REQUIRED_FOR: an ordinary story claims no category, because a
    category a reviewer was forced to pick is one nobody observed.
    """
    verdict = str(verdict).strip()
    if verdict not in VERDICTS:
        raise ValueError(
            f"verdict must be one of {VERDICTS}, not {verdict!r}"
        )
    if verdict in KIND_REQUIRED_FOR and not str(kind).strip():
        raise ValueError(
            f"a {verdict} verdict needs the kind: a count of which kind, "
            "against a rule or a publisher, is what a fix is built from"
        )
    when = decided_at or datetime.now(UTC)
    note = {
        "verdict": verdict,
        # Empty for an ordinary story. Kept as a key rather than dropped,
        # so a reader can tell "no category claimed" from "written by
        # something older than this field".
        "kind": str(kind).strip(),
        "decided_at": when.isoformat() if hasattr(when, "isoformat") else str(when),
    }
    # Optional: useful in an audit trail, never required to act on.
    if str(decided_by).strip():
        note["decided_by"] = str(decided_by).strip()
    return note


def missing_keys(note) -> list[str]:
    """Which required keys this verdict lacks or leaves empty.

    `kind` counts only where the verdict requires it. A story with no
    category is a complete answer -- the commonest one -- and reading it
    as unusable would throw away every ordinary story a reviewer
    restored.
    """
    if not isinstance(note, dict):
        return list(REQUIRED_KEYS)

    def absent(key):
        value = note.get(key)
        # `str(None)` is "None", which is not empty -- a None value passes
        # a naive truthiness check and the verdict would read as usable.
        return value is None or not str(value).strip()

    wanted = list(REQUIRED_KEYS)
    if str(note.get("verdict", "")).strip() in KIND_REQUIRED_FOR:
        wanted.append("kind")
    return [key for key in wanted if absent(key)]


def is_readable(note) -> bool:
    """Can the pipeline act on this verdict?"""
    return not missing_keys(note)


def read(note) -> dict:
    """The verdict, or raise saying what is missing."""
    absent = missing_keys(note)
    if absent:
        raise UnreadableVerdict(
            "a discovery verdict is missing " + ", ".join(absent)
        )
    return dict(note)


def status_for(note) -> str | None:
    """The status the article should carry, from the reviewer's verdict.

    None where the verdict does not decide it: `news` and `column` are
    ordinary stories and take whatever the pipeline's own classification
    gives them. This only overrides where a person named a type the
    pipeline keeps out of enrichment.
    """
    if not is_readable(note):
        return None
    if note["verdict"] != IS_A_STORY:
        return None
    # Empty is the ordinary story: the pipeline's own classification
    # stands, which is the whole point of not making somebody choose.
    kind = str(note.get("kind") or "").strip()
    return kind if kind in UNENRICHED_TYPES else None


def link_status_for(note) -> str:
    """The status the candidate link should carry, from the verdict.

    `status_for` answers what an ARTICLE should be once one exists. This
    answers whether one should exist at all, which is a different question
    and the reason it is a separate function: the article status is read
    after a fetch, and this is read instead of one.

    `VERIFIED_STATUS` for an ordinary story: the person has verified it,
    and it waits to be fetched. NOT `discovered`, which is verification's
    own input -- see the constant.

    The kind itself for anything in `UNFETCHED_TYPES`, which keeps it out
    of the fetch queue: recording the kind IS the instruction not to
    fetch.

    Anything not a usable story verdict also returns the kind or the
    verified status rather than raising, because a caller in the middle of
    writing one row cannot do anything useful with an exception here.
    """
    if not is_readable(note) or note["verdict"] != IS_A_STORY:
        return VERIFIED_STATUS
    kind = str(note.get("kind") or "").strip()
    return kind if kind in UNFETCHED_TYPES else VERIFIED_STATUS
