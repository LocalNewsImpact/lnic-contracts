# Shared build machinery

This repository holds two things for the suite: the shapes one service
writes and another reads, and the workflows that build and check them.

They are versioned separately, in one repository, under two tag series:

| Tag | What it versions | How a consumer pins it |
| --- | --- | --- |
| `v0.2.0` | the Python package | `lnic-contracts @ https://.../archive/refs/tags/v0.2.0.tar.gz` |
| `ci-v1.0.0` | one iteration of the workflows, recorded | pin it where you need exactly this |
| `ci-v1` | what consumers normally pin; follows the latest v1 | `uses: .../python-checks.yml@ci-v1` |

### Two CI tags, because they do different jobs

`ci-v1.2.3` never moves, so "what ran on 4 September" has an answer and a
consumer that needs to pin exactly can. `ci-v1` follows it, so a fix
reaches all three repositories without a pull request in each one.

Either alone is worse. A moving major tag with no versions under it --
which is what this repository had -- records nothing: `ci-v1` was moved
by hand twice in one day and there was no way to say what it had been.
Versions with no moving tag propagate nothing: every fix becomes a bump
in every consumer.

The safety is not that a tag cannot move. It is that the major tag only
moves after the release's own checks pass, which is what
`release-ci.yml` does: push `ci-v1.1.0`, it runs `make check`, and only
then does `ci-v1` follow.

Two series because the cadences differ. A workflow is edited often and
affects nothing at runtime; the package defines a shape two services must
agree on, and changing it strands data if they disagree. One tag series
for both would mean a CI tweak bumping the version of a data contract
that had not changed, and "what is in 0.3.0" would stop being answerable.

A workflow reference is a git ref, not a pip install, so pinning them
separately costs nothing.

### What a version covers, and what changes it

Two series, two universes. A change outside a series' universe does not
version it.

**`vX.Y.Z` — the Python package.** `src/lnic_contracts/**` and the parts
of `pyproject.toml` that decide what installs. The sdist carries the
whole repository, but setuptools packages `src/` only, so a workflow
edit changes the tarball's bytes and not one thing a consumer imports.

| | The package |
| --- | --- |
| MAJOR | a consumer must change code to keep working: a key renamed or removed, a function gone, or the MEANING of one changed |
| MINOR | something added that a consumer may use: a new function, a new optional key |
| PATCH | a fix that changes nothing a consumer depends on |

The important case is not the Python signature. **Renaming a key inside
`articles.metadata` is MAJOR even when every function keeps its name**,
because the producer and the consumer then disagree at runtime and
articles strand held with no way to release them. That failure is the
reason this package exists, and it does not show up as an import error.

**`ci-vX.Y.Z` — the CI.** The `workflow_call` workflows
(`python-checks.yml`, `conforms.yml`, `image-build.yml`) and
`.github/actions/**`. Not `ci.yml` or `release-ci.yml`: those are this
repository's own and nobody calls them.

| | The CI |
| --- | --- |
| MAJOR | a caller must change its call, or a repository that was passing starts failing: an input renamed, removed or newly required; a job removed; **a new rule in `conforms.yml`** |
| MINOR | a new optional input, or a job that is off by default |
| PATCH | a fix inside a step that changes no interface |

**A new conformance rule is a breaking change.** It arrives through the
moving `ci-v1` with no pull request in any repository, and every one of
them goes red at once for something none of them changed. New rules ship
as `ci-v2`, and repositories move to it when they are ready to satisfy
it.

Neither series versions documentation, tests, or the README.

---

## The CI pattern

`python-checks.yml` runs the suite's stages, in order, with a Postgres
service:

    lint  ->  typecheck  ->  test  ->  integration

`conforms.yml` fails a repository that has drifted from it.

### Every stage is a make target

Not `ruff check .`, not `pytest -m ...`. `make lint`, `make test`. The
commands live in each repository's Makefile, which is also what a person
runs on their own machine, **so CI and a local run cannot mean different
things**.

That is the failure this exists to end. On 4 September a crawler pull
request failed on an integration test that could not be run locally at
all: an autouse fixture wrote the ORM schema into whatever DATABASE_URL
named, alembic then failed, so nobody ran them, so a broken test reached
CI. The tests were fine. What was missing was one command that meant the
same thing in both places.

### What is shared, and what is not

Shared: the stages, their order, the Postgres service, the Python
version, and the rule that a stage is a make target.

Not shared: what the targets do. The crawler runs its tests inside a
prebuilt image because its dependencies take minutes to install;
datadesk installs them on the runner because they take seconds. Both are
`make test`.

### Adopting it

```yaml
name: CI
on: [push, pull_request]

jobs:
  checks:
    uses: LocalNewsImpact/lnic-contracts/.github/workflows/python-checks.yml@ci-v1
    with:
      integration: true
  conforms:
    uses: LocalNewsImpact/lnic-contracts/.github/workflows/conforms.yml@ci-v1
    with:
      integration: true
```

The repository provides `make lint`, `make test`, and — where it declares
them — `make typecheck` and `make test-integration`, plus
`scripts/setup-hooks.sh` so a red push is refused before CI sees it.

### Authentication is the same everywhere

Every repository exposes two variables, so a shared workflow names them
without knowing which project it is in:

| | |
| --- | --- |
| `vars.WIF_PROVIDER` | the workload identity provider |
| `vars.DEPLOY_SERVICE_ACCOUNT` | the account to impersonate |

They were three different things -- a service-account JSON key in one
repository, a variable in another, a provider path hardcoded in a
workflow file in the third -- which is why a shared workflow could not
name a secret. Normalised on 4 September; the crawler's project had no
GitHub identity pool at all until then.

---

## Why the image workflow exists

Every image failure in this suite has had one shape: something decided
what was in an image, and nothing checked that the image matched it.

**The CI image was seven weeks old.** The crawler's `ci-base` was built on
18 July and its `base` on 3 September. Nothing rebuilds one when the other
changes and nothing compares them, so CI ran for seven weeks against an
image that could not hold what the commits pinned. A hundred collection
errors, in three jobs, none naming the cause. PR #498 was merged with them
failing.

**A pull request could not test its own dependency bump.** The image is
built at merge; a pull request that changes `requirements-base.txt` is
tested against an image built from the previous version of that file. The
workaround was already in the repository -- two test commands carried a
one-package `pip install`, added when somebody hit the same wall.

**A package was pinned twice and the stale pin won.** datadesk's base
installed `lnic-contracts` from `requirements.txt` and again from a
Dockerfile ARG defaulting to the older version. The image reported 0.2.0
and carried v0.1.0's code, and `/review/queue/` raised AttributeError on
submit for a function that was in the version the metadata claimed.
Removing the bad line changed nothing deployed, because the base image's
hash did not cover the Dockerfile that built it.

### Two pieces, because the builds differ

`.github/actions/image-tag` answers one question: given everything that
goes into an image, what should it be tagged, and is it already built?

`.github/workflows/image-build.yml` uses that action and then builds on a
GitHub runner.

The split is not tidiness. The first version was the workflow alone, and
it could only ever have served datadesk: its images are around 300 MB,
while the crawler's are 1.4-10 GB built from a 6.4 GB context, which is
why the crawler builds in Cloud Build and cannot build on a runner. The
part worth sharing was never the build. It is the question, and the answer
has to be usable by a caller that then builds however it builds:

```yaml
- uses: LocalNewsImpact/lnic-contracts/.github/actions/image-tag@ci-v1
  id: base
  with:
    image: us-central1-docker.pkg.dev/mizzou-news-crawler/mizzou-crawler/base
    dockerfile: Dockerfile.base
    inputs_to_hash: requirements-base.txt

- if: steps.base.outputs.exists == 'false'
  run: |
    gcloud builds submit --config gcp/cloudbuild/cloudbuild-base.yaml \
      --substitutions=_TAG=${{ steps.base.outputs.tag }}
```

### What replaces it

The crawler decides what to rebuild from hand-written regexes over changed
file paths -- one per service, each listing the source directories that
service uses:

```
if echo "$CHANGED_FILES" | grep -qE 'Dockerfile\.processor|requirements-processor\.txt|src/(models|pipeline|utils|...)/'
```

A path missing from one of those lists is a service that silently stops
being rebuilt. That has happened: `src/crawler` was absent from the
processor's list.

`image-build.yml` does not ask what changed. It hashes what goes into the
image -- the Dockerfile, the requirements, the source trees it copies, the
build arguments -- and uses the hash as the tag:

```yaml
jobs:
  base:
    uses: LocalNewsImpact/lnic-contracts/.github/workflows/image-build.yml@ci-v1
    with:
      image: us-central1-docker.pkg.dev/lnic-datadesk/app/datadesk-base
      dockerfile: Dockerfile.base
      inputs_to_hash: |
        requirements.txt
      build_args: |
        DIRECTORY_VERSION=${{ needs.resolve.outputs.version }}
      project: lnic-datadesk
      workload_identity_provider: ${{ vars.WIF_PROVIDER }}
      service_account: ${{ vars.DEPLOY_SA }}
```

An image for that content either exists, in which case there is nothing to
do, or it does not, in which case it is built. There is no path list to
keep in step with the Dockerfile, no way for a change to be reused away,
and "what is deployed" is answerable by reading the tag.

A path named in `inputs_to_hash` that does not exist fails the build. A
typo there would otherwise silently stop tracking a real input, which is
the failure this is replacing.

---

## What is not here

**Deployment.** The crawler runs migrations as a Cloud Run job, deploys a
candidate revision with no traffic, proves it on its own tagged URL, and
shifts traffic only if it answers. datadesk does the same with a smoke
job in front of the shift. Those are worth sharing eventually and are not
shared yet: the shapes differ enough (one service against four, one
database against two) that a premature abstraction would be harder to
read than the two copies.

**The GHCR mirror.** The crawler mirrors Artifact Registry to GHCR because
pulling multi-GB images to GitHub runners costs $0.35–0.50 each in egress.
datadesk's images are around 300 MB and do not need it. Content-hashed
tags make a mirror easier to reason about -- a tag that is not there fails
loudly instead of pulling something older -- but the mirror itself stays
where it is used.

**Adoption.** No repository calls these workflows yet. The plan is
`MizzouNewsCrawler/docs/BUILD_AND_CI_ARCHITECTURE.md`, which sequences it:
hash-keyed images first, then the base image's contents, then the
requirements files, then the shared workflows, then the enrichment split.
