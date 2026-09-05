# lnic-contracts

Shapes that one service in the suite writes and another reads.

## The suite

This repository holds two things the other three depend on: the shapes
they exchange, and the machinery that checks them. What follows is the
whole arrangement in one place; `docs/shared-ci.md` carries the detail.

### The repositories

| Repository | What it is | What it publishes |
| --- | --- | --- |
| `MizzouNewsCrawler` | discovery, extraction, cleaning, classification and enrichment; GKE + Argo Workflows | rows in the crawler database; analytics tables in BigQuery |
| `datadesk` | the newsroom console and review queue; Django on Cloud Run | decisions written back to the crawler database; published visuals |
| `NewsSourceDirectory` | the outlet directory and its review queue; Django on Cloud Run at `sources.localnewsimpact.org` | a hashed static feed on `gh-pages`, read by the WordPress plugin |
| `lnic-contracts` | the shapes one service writes and another reads, the shared CI, the coverage floor | a Python package and two tag series |

### How main is protected

Two layers, deliberately split.

**One organization ruleset**, `Main is reached by pull request`, targets `~ALL` repositories' default branch:

| Rule | Effect |
| --- | --- |
| `pull_request` | a change reaches main through a pull request; one approving review, code-owner review where a CODEOWNERS file matches |
| `non_fast_forward` | no force-push over main |
| `deletion` | main cannot be deleted |

**Each repository's own ruleset** carries `required_status_checks` and nothing else. That rule cannot move up to the organization: the contexts differ per repository — `checks / integration` exists only in the crawler, `Data quality`, `Public feed`, `Pages payload` and `Image builds` only in the Source Directory — and a context named in a ruleset but never reported blocks every pull request permanently.

The rules the suite works to:

1. Nothing is pushed to origin except on a branch.
2. Every repository has a pre-push hook that runs `make check`, so what CI will say is known before it is said.
3. CI checks the pull request, and green is what allows a merge.
4. An administrator may merge without a code review.
5. Nobody pushes to main, administrators included.

Four and five look contradictory. The ruleset's bypass list resolves them, and the mode is what does it: `OrganizationAdmin` bypasses in `pull_request` mode, which permits an override **while merging a pull request** and none at all for a direct push.

| Bypass mode | Direct push to main | Merge against the rules |
| --- | --- | --- |
| `always` | allowed | allowed |
| `pull_request` (in use) | refused | allowed, with `--admin` |

So an administrator merges with `gh pr merge <n> --squash --admin`, and a merge without `--admin` waits for a review. The GraphQL field `viewerCanMergeAsAdmin` reports `false` under this configuration and the `--admin` merge succeeds anyway; it describes the legacy branch-protection override, not a ruleset bypass, and is not the field to read.

`delete_branch_on_merge` is on in every repository.

### What enforces what

| Layer | Catches | Where it lives |
| --- | --- | --- |
| pre-push hook | a red commit, before it leaves the machine | `scripts/setup-hooks.sh`, one per repository, running that repository's `make check` |
| shared CI | a red pull request | `lnic-contracts/.github/workflows/python-checks.yml@ci-v1` — lint, typecheck, test, integration, with a Postgres service |
| `conforms.yml` | a repository drifting from the pattern | `lnic-contracts`, called alongside the checks |
| the ruleset | a merge that skipped either | GitHub, organization and repository level |

`conforms.yml` fails a repository that stops calling the shared workflow, loses a make target the workflow runs, drops its pre-push hook, lets that hook run the whole suite for a branch deletion, leaves CI's push trigger unscoped so every pull request push runs twice, sets a coverage floor of its own, or stops running the suite's floor from `make test`.

Every stage is a make target — `make lint`, `make test` — never a bare `ruff` or `pytest`. The commands live in each repository's Makefile, which is what a person runs locally, so CI and a local run cannot mean different things. What the targets *do* differs: the crawler runs its tests inside a prebuilt image because its dependencies take minutes to install; the others install them on the runner because they take seconds. Both are `make test`.

The coverage floor is one number, 80%, in `lnic_contracts.coverage_floor`, run by every repository's `make test` and again by the shared workflow. A repository that sets its own is refused.

### How the repositories are joined

**Data.** One Cloud SQL instance serves all three applications. The crawler owns its database; the Source Directory's tables live in a `directory` schema alongside shared identity tables in `public`; datadesk has its own database and reaches the crawler's through a **read-only role** (`infra/sql/create_crawler_readonly_role.sql`, password in Secret Manager), with a separate read-write connection for the decisions the review queue writes back. Postgres enforces the read-only half; it is not a convention.

**Packages.** `lnic-contracts` is installed from a tag tarball, pinned in each consumer's requirements. `NewsSourceDirectory` is installed into datadesk's base image from a pinned git tag, so the directory front end datadesk serves is a released version rather than whatever `main` happens to be; tagging a directory release dispatches datadesk's deploy.

**Versioning.** `lnic-contracts` carries two tag series, because the cadences differ. `vX.Y.Z` versions the Python package — the shapes two services must agree on, where a renamed key strands data at runtime with no import error to catch it. `ci-vX.Y.Z` versions the workflows, and `ci-v1` follows the newest of them, so a CI fix reaches all three repositories without a pull request in each. `release-ci.yml` runs `make check` before moving the major tag.

**Publishing.** The crawler exports to BigQuery. The Source Directory publishes a hashed static feed to `gh-pages`, which the WordPress plugin reads. datadesk publishes visuals.

### This repository's place in it

Everything above that is not a GitHub setting is defined here.

| What | Where |
| --- | --- |
| the stages, their order, the Postgres service | `.github/workflows/python-checks.yml` |
| the rules a repository must still satisfy | `.github/workflows/conforms.yml` |
| the coverage floor, one number for the suite | `src/lnic_contracts/coverage_floor.py` |
| how an image is tagged by its contents | `.github/actions/image-tag` |
| the shapes services exchange | `src/lnic_contracts/` |

A consumer pins `python-checks.yml@ci-v1`, so a change here reaches all
three repositories with no pull request in any of them. That is the
point and the hazard: a new `conforms.yml` rule arrives the same way, and
a repository that does not satisfy it goes red for something it did not
change. The rule is therefore to land the fix in every repository first
and move the tag last, which makes the release MINOR; the alternative,
for a rule some repository cannot yet satisfy, is `ci-v2`. What is never
done is moving `ci-v1` onto a rule a consumer is known to fail -- the
three pull requests it breaks include the one that would fix it.

`release-ci.yml` is the gate the moving tag waits behind: push
`ci-v1.6.0`, it runs `make check`, and only then does `ci-v1` follow.

---

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
