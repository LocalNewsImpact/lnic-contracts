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

#: The status a link goes back to so the pipeline fetches it again.
RESTORED_STATUS = "discovered"

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

#: What the verdict must carry, and why each one:
#:
#: verdict   story or not_story. What the reviewer answered.
#: kind      what kind of story, or what it is instead. The half that
#:           tells the pipeline where to put the article; without it a
#:           restored URL is re-classified from scratch.
#: decided_at  when. A verdict older than the last re-verification is a
#:           verdict about a different answer.
REQUIRED_KEYS: tuple[str, ...] = ("verdict", "kind", "decided_at")


class UnreadableVerdict(ValueError):
    """A verdict the pipeline cannot act on."""


def build(*, verdict: str, kind: str, decided_at=None, decided_by: str = "") -> dict:
    """The verdict to write when a reviewer answers a discovery row."""
    verdict = str(verdict).strip()
    if verdict not in VERDICTS:
        raise ValueError(
            f"verdict must be one of {VERDICTS}, not {verdict!r}"
        )
    if not str(kind).strip():
        raise ValueError(
            "a verdict needs the kind: without it a restored URL is "
            "re-classified by the model that got it wrong"
        )
    when = decided_at or datetime.now(UTC)
    note = {
        "verdict": verdict,
        "kind": str(kind).strip(),
        "decided_at": when.isoformat() if hasattr(when, "isoformat") else str(when),
    }
    # Optional: useful in an audit trail, never required to act on.
    if str(decided_by).strip():
        note["decided_by"] = str(decided_by).strip()
    return note


def missing_keys(note) -> list[str]:
    """Which required keys this verdict lacks or leaves empty."""
    if not isinstance(note, dict):
        return list(REQUIRED_KEYS)

    def absent(key):
        value = note.get(key)
        # `str(None)` is "None", which is not empty -- a None value passes
        # a naive truthiness check and the verdict would read as usable.
        return value is None or not str(value).strip()

    return [key for key in REQUIRED_KEYS if absent(key)]


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
    kind = str(note["kind"]).strip()
    return kind if kind in UNENRICHED_TYPES else None
