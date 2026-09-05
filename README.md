# lnic-contracts

Shapes that one service in the suite writes and another reads.

## Why this exists

The suite is becoming four or five applications over one database, and the
boundaries between them are still moving:

- crawling and cleaning
- analysis and enrichment  (being split out of the crawler)
- datadesk — review and published visuals
- the source directory — which is to own the `sources` table the crawler
  owns today

Each split turns something that was an internal function call into a
handover between services, and every handover has a shape. Nothing enforced
those shapes.

That is why this is a package and not a document: the couplings arrive
faster than the conventions, and a contract nobody imports is a convention.

The review hold is the case that forced it. The crawler writes a note into
`articles.metadata.review` saying what it held and what to restore; the
datadesk console reads that note to form its question and put the article
back. A key renamed on either side is invisible until an article is held
and cannot be released — and then it is stranded, out of the pipeline, with
the status it was held from gone.

Both sides had a test asserting the key set. Neither test could see the
other. This package is the one definition they both import.

## Coming, as the splits land

`sources` moving to the directory makes the publisher record a handover
rather than a table the crawler owns — the largest one in the suite, and
the one datadesk already mirrors 134 fields of by hand.

Separating analysis and enrichment from crawling makes the article handover
a boundary too: what cleaning promises, and what enrichment may assume.

## What belongs here

A shape that crosses a service boundary. Not a database schema — the
crawler owns that and datadesk mirrors it — and not application logic.
Just the agreed shape of something handed over, and the smallest code
needed to build and read it correctly.

One thing here is not a shape: `coverage_floor`, the suite's 80 percent,
which every repository's `make test` and the shared CI workflow both run.
It lives in the package because that is what every repository already
installs, and a rule each repository restates is a rule that drifts.
The workflows themselves are in `docs/shared-ci.md`.

## What does not

Anything only one service uses. A contract with one consumer is a module,
and it belongs in that service.

## Versioning

Adding an optional key is a minor version. Renaming or removing one is
major, and requires every consumer to move — which is the point: the
version bump is the conversation that a silent rename skipped.
