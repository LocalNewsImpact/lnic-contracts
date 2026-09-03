"""The crawler has held an article; the console has to be able to release it.

WHAT THIS IS FOR
----------------
When the crawler finds a field that is wrong rather than absent -- a byline
holding "Admin" instead of a name, a body still in ROT47 ciphertext -- it
stops the article instead of exporting it. The article goes to `in_review`,
a status no pipeline stage selects, and waits for a person.

Holding it overwrites `status`, so two things have to be recorded elsewhere:
the status to put it back on, and the claim being reviewed. Both live in
`articles.metadata` under `review`.

WHY IT IS SHARED CODE AND NOT A CONVENTION
------------------------------------------
The crawler writes the note. The datadesk console reads it, forms its
question from the claim, and restores the status on Accept. Each repository
had a test asserting the four keys, and neither test could see the other, so
a key renamed on one side was invisible until an article was held and could
not be let out -- stranded, out of the pipeline, with the status it was held
from gone.

One definition, imported by both. Renaming a key here breaks the build of
every consumer, which is the conversation a silent rename skipped.
"""

from __future__ import annotations

from datetime import datetime, timezone

#: The status a held article carries. Selected by no pipeline stage:
#: labeling reads `cleaned`/`local`, enrichment reads `labeled`.
IN_REVIEW = "in_review"

#: Where the note lives inside `articles.metadata`.
METADATA_KEY = "review"

#: What the note must carry, and why each one:
#:
#: status_before  what to restore on Accept. Without it the article is
#:                stranded: `status` says in_review and says nothing else.
#: claim          what is being reviewed. `status` no longer says, so the
#:                console cannot form its question without this.
#: stage          which step raised it. The console keys its question on
#:                claim AND stage, so the same claim from two steps stays
#:                two questions.
#: held_at        when. A queue that cannot say how long something has
#:                waited cannot show that reviews are piling up.
REQUIRED_KEYS: tuple[str, ...] = ("status_before", "claim", "stage", "held_at")


class UnreadableNote(ValueError):
    """A note that cannot release the article it is attached to."""


def build(*, claim: str, status_before: str, stage: str, held_at=None) -> dict:
    """The note to write when holding an article.

    `status_before` is the status the article carried BEFORE the hold. Read
    it before overwriting `status`, not after: taken afterwards it records
    `in_review`, and the article can never be put back.
    """
    if not str(claim).strip():
        raise ValueError("a hold needs a claim: what is being reviewed")
    if not str(status_before).strip():
        raise ValueError(
            "a hold needs the status it is holding, or the article cannot be "
            "released"
        )
    if str(status_before).strip() == IN_REVIEW:
        raise ValueError(
            "status_before is in_review, which means it was read after the "
            "hold was applied; read it before"
        )
    if not str(stage).strip():
        raise ValueError("a hold needs the stage that raised it")
    when = held_at or datetime.now(timezone.utc)
    return {
        "status_before": str(status_before).strip(),
        "claim": str(claim).strip(),
        "stage": str(stage).strip(),
        "held_at": when.isoformat() if hasattr(when, "isoformat") else str(when),
    }


def missing_keys(note) -> list[str]:
    """Which required keys this note lacks or leaves empty.

    An empty value is as bad as an absent key: neither can restore an
    article or name a question.
    """
    if not isinstance(note, dict):
        return list(REQUIRED_KEYS)

    def absent(key):
        value = note.get(key)
        # `str(None)` is "None", which is not empty -- so a None value
        # passed a naive truthiness check and a note carrying one would
        # have been called readable.
        return value is None or not str(value).strip()

    return [key for key in REQUIRED_KEYS if absent(key)]


def is_readable(note) -> bool:
    """Can this note release the article it is attached to?"""
    return not missing_keys(note)


def read(note) -> dict:
    """The note, or raise saying what is wrong with it.

    For a caller that cannot proceed without it. A caller that can -- a
    queue drawing a row -- should use `missing_keys` and say so on the page
    rather than failing, because an article nobody can release is something
    a person needs to see, not an exception in a log.
    """
    absent = missing_keys(note)
    if absent:
        raise UnreadableNote(
            "a held article cannot be released: the note is missing "
            f"{', '.join(absent)}"
        )
    return dict(note)


def from_metadata(metadata) -> dict:
    """The note out of an article's metadata, or {}.

    Accepts the JSON string the crawler writes as well as a decoded dict,
    because the two services reach the column through different layers.
    """
    if isinstance(metadata, str):
        import json

        try:
            metadata = json.loads(metadata)
        except ValueError:
            return {}
    if not isinstance(metadata, dict):
        return {}
    note = metadata.get(METADATA_KEY)
    return note if isinstance(note, dict) else {}


def into_metadata(metadata, note: dict) -> dict:
    """`metadata` with the note added, leaving everything else alone.

    Refuses to overwrite an existing note: re-holding would replace the
    status the article was first held from, which is the one thing that
    can put it back.
    """
    meta = dict(metadata or {})
    if METADATA_KEY in meta:
        return meta
    meta[METADATA_KEY] = note
    return meta
