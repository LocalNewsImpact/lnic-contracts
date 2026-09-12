"""A review decision has rewound a record; a crawler stage has to pick it up.

WHAT THIS IS FOR
----------------
Every crawler stage selects by status, and a rewound record shares its
status with the whole backlog. The 14 articles a reviewer sent back to
`cleaned` sit beside 450 the pipeline put there, and a stage told only
"classify what is at `cleaned`" cannot tell them apart. The first nightly
housekeeping run could not, and began extracting 4,802 candidate links
when the dispositions accounted for 45.

So the rewind is recorded as a row, in `pipeline_rework`: one per
(record, stage) still owed work. The console writes a row when it rewinds
a record. The stage reads its own rows and nothing else, closes them with
an outcome, and queues the stage after it. An empty table means nothing
to do -- never "no filter", which is the inversion that turns a targeted
run into a sweep.

WHY IT IS SHARED CODE AND NOT A CONVENTION
------------------------------------------
The console writes the rows and the crawler reads them, and each side had
its own copy of the stage names and of the status each stage selects. A
row written against the wrong status is not an error anywhere: it is
accepted, it is never selected, and it stays open forever -- so the
nightly guard sees work owed, every stage runs, and nothing happens. That
failure is silent on both sides and invisible to either repository's
tests.

The pairing is the load-bearing part. `extract` selects a LINK at
`article`; `classify` selects an ARTICLE at `cleaned` or `local`;
`enrich` selects an ARTICLE at `labeled`. Setting an article to `article`
-- a link status -- schedules nothing at all, and an earlier draft of the
console's reconciler did exactly that.

WHAT IS NOT HERE
----------------
Discovery and URL verification. Housekeeping starts at records ready for
extraction: a link a reviewer restored goes back to `discovered`, which
is verification's input, and verification is the pipeline's own cron. A
row naming a stage housekeeping does not run is a row nobody will ever
close.
"""

from __future__ import annotations

#: The table. Owned by the crawler's schema (alembic x9y0z1a2b3c4); named
#: here because the console writes to it and reads it by name.
TABLE = "pipeline_rework"

#: What a row can be about. The record type decides which table the id is
#: in, and ids are only unique within their own table.
CANDIDATE_LINK = "candidate_link"
ARTICLE = "article"
RECORD_TYPES: tuple[str, ...] = (CANDIDATE_LINK, ARTICLE)

#: The stages housekeeping runs, in the order it runs them.
EXTRACT = "extract"
CLASSIFY = "classify"
ENRICH = "enrich"
STAGES: tuple[str, ...] = (EXTRACT, CLASSIFY, ENRICH)

#: What each stage is about, and the status it selects. A row outside this
#: mapping is accepted by the database and selected by nothing.
#:
#: `classify` takes two statuses because `analyze` defaults to
#: `['cleaned', 'local']`: `local` is the wire-check verdict carried on an
#: article the pipeline decided is local, and both are classifiable.
SELECTS: dict[str, tuple[str, tuple[str, ...]]] = {
    EXTRACT: (CANDIDATE_LINK, ("article",)),
    CLASSIFY: (ARTICLE, ("cleaned", "local")),
    ENRICH: (ARTICLE, ("labeled",)),
}

#: Which stage follows which, once one finishes. The stage that finishes
#: writes the next row, not the console: extraction's article does not
#: exist until the fetch, so nothing upstream knows its id.
FOLLOWS: dict[str, str | None] = {
    EXTRACT: CLASSIFY,
    CLASSIFY: ENRICH,
    ENRICH: None,
}

#: Where the chain ends. An article at one of these is in the export --
#: which is the point of carrying it -- and owes nothing further.
PUBLISHED: tuple[str, ...] = ("enriched", "enrichment_skipped")


def record_type_for(stage: str) -> str:
    """Which kind of record `stage` works on."""
    _known(stage)
    return SELECTS[stage][0]


def selects(stage: str) -> tuple[str, ...]:
    """The statuses `stage` selects."""
    _known(stage)
    return SELECTS[stage][1]


def next_stage(stage: str) -> str | None:
    """The stage that follows `stage`, or None at the end of the chain."""
    _known(stage)
    return FOLLOWS[stage]


def check(*, stage: str, record_type: str, status: str) -> None:
    """Raise unless a row for (stage, record_type, status) can be selected.

    Called by the writer, before the row exists. A row that cannot be
    selected fails nowhere: the insert succeeds, no stage takes it, the
    nightly guard counts it as work owed, and every stage runs for
    nothing. This is the only place that mismatch is detectable.
    """
    _known(stage)
    wanted_type, wanted_statuses = SELECTS[stage]
    if record_type != wanted_type:
        raise ValueError(
            f"{stage} works on a {wanted_type}, not a {record_type}: "
            f"a row it cannot select is a row nobody closes"
        )
    if status not in wanted_statuses:
        raise ValueError(
            f"{stage} selects {wanted_statuses}, and this {record_type} is "
            f"{status!r}: the record has to already be where the stage looks"
        )


def _known(stage: str) -> None:
    if stage not in STAGES:
        raise ValueError(
            f"{stage!r} is not a housekeeping stage. One of {STAGES}. "
            "Discovery and URL verification are the pipeline's own crons, "
            "and a row naming a stage housekeeping does not run is a row "
            "nobody will ever close."
        )
