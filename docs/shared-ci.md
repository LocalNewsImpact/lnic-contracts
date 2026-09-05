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

**A new rule is breaking when a repository that passes would fail.** A
rule arrives through the moving `ci-v1` with no pull request in any
repository, so a repository that does not satisfy it goes red for
something it did not change. Two ways to ship one:

- **Land it in every repository first, move the tag last.** Each
  repository's pull request is green under the current tag; when the
  tag moves, nothing that was passing starts failing, and the release is
  MINOR. This is how the coverage floor shipped (`ci-v1.4.0`).
- **`ci-v2`**, when the first is not possible -- a rule some repository
  cannot yet satisfy -- and repositories move to it when they are ready.

What is never done: moving `ci-v1` onto a rule a consumer is known to
fail. The three pull requests it breaks include the one that would fix it.

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
version, the coverage floor, and the rule that a stage is a make target.

Not shared: what the targets do. The crawler runs its tests inside a
prebuilt image because its dependencies take minutes to install;
datadesk installs them on the runner because they take seconds. Both are
`make test`.

### The coverage floor is one number, here

Eighty percent of lines, across the suite. It is `FLOOR` in
`lnic_contracts.coverage_floor`, and nowhere else.

It was in four places and none of them said 80: the crawler said 78 in
two files, the Source Directory 78 in one, datadesk and this repository
nothing at all. Each was green against itself, so nothing said the suite
had drifted from its own rule. A number restated per repository is a
number per repository.

Two things run the same file:

- **`make test`**, in every repository, after pytest writes the report:

      pytest --cov --cov-report=xml
      python -m lnic_contracts.coverage_floor coverage.xml

  so the pre-push hook refuses what CI would.

- **`python-checks.yml`**, after `make test`, from the commit the
  caller's `@ci-vN` resolved to (`github.job_workflow_sha`) -- not from
  whatever version of the package the repository installed, so the
  number CI enforces is the one the tag ships.

`conforms.yml` refuses a repository that carries a `fail_under` or
`--cov-fail-under` of its own, and one whose `make test` does not run the
floor. To change the floor, change `FLOOR`, and every repository moves
together. It only goes up.

The comparison is exact: 79.96% is under 80%. coverage.py's own
`fail_under` rounds the total to its `precision` first (0 by default), so
79.5% passes an 80 there. A report that measured no lines is not a pass
either -- `--cov` pointed at a package that does not exist reports a rate
of 1.0, and the floor calls that not measured.

What counts as covered is still each repository's: `[tool.coverage.run]
source` and `omit` say what the code is (migrations and tests are not).
The floor says how much of it a test must reach.

### Local databases do not share ports

Each repository's compose Postgres publishes on a port of its own, and the
target that starts it checks who is answering there, because one of the
two ways a port can be taken is silent.

Another **container** on the port is loud: `compose up` fails with `Bind
for 0.0.0.0:5434 failed: port is already allocated` and nothing starts.
A **host process** on the port is not: Docker Desktop starts the
container anyway, `docker ps` reports the binding, `compose up --wait`
reports it healthy (the health check runs inside the container), and the
host process keeps answering. The repository's tests then run against
whatever that process is. Measured on 2026-09-05 with a plain socket
listening on 5435: `datadesk-test-postgres` came up "Healthy" and
`compose port` said `0.0.0.0:5435`, while the socket held the port.

Checking the port the container was given does not catch this -- Docker
reports the port it asked for. datadesk's `make test-db` asks Postgres
instead: `pg_control_system().system_identifier` inside the container and
through the host port must be the same cluster.

| Port | Repository | Container |
| --- | --- | --- |
| 5432 | MizzouNewsCrawler | `mizzou-postgres` |
| 5434 | NewsSourceDirectory | `nsd-postgres` |
| 5435 | datadesk | `datadesk-test-postgres` |

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
`make test` writes `coverage.xml` and runs the suite's floor on it; the
repository has `lnic-contracts` installed, as a dev dependency if nothing
else imports it.

### Stages that run inside an image

The `install` input is how a repository provides what its targets need
before each stage runs. datadesk and the Source Directory pass
`make .venv`; the crawler passes `make ci-image`, which logs in to GHCR
and pulls the image its targets then `docker run`. Two things make that
possible, and both are easy to remove by accident:

- The install step runs with `GITHUB_TOKEN` in its environment. The
  token is otherwise not an environment variable at all, and the
  string a caller passes cannot reference secrets.
- `python-checks.yml` declares no `permissions` of its own, so its jobs
  run with whatever the caller granted. A called workflow can only
  narrow its caller's grant, so a `contents: read` block here would be a
  ceiling under which a private-image pull -- `packages: read` -- can
  never fit, and the failure ("requesting packages: read, but is only
  allowed packages: none") would point at the wrong repository.

The caller says what it needs:

```yaml
permissions:
  contents: read
  packages: read   # the CI image is a private package on GHCR

jobs:
  checks:
    uses: LocalNewsImpact/lnic-contracts/.github/workflows/python-checks.yml@ci-v1
    with:
      install: make ci-image
```

A stage command must be the same string whether it runs on a developer's
virtualenv or inside the image; only the wrapper around it may differ.
That is what makes `make test` one definition rather than two.

### `fetch-tags`, for a repository that tests its own tags

Off by default: a tag fetch is not free and most stages have no use for
one. Turn it on where the suite is checked against them.

The Source Directory is the case that produced it. It asserts that the
version in `pyproject.toml` is not one already released — a merge into a
version that is tagged cannot be released, and main should never sit in
that state. Under the default shallow checkout the test found no tags at
all, took its "no tags, nothing to check" path, and passed. Main was
green while sitting in exactly the state the test exists to prevent, and
only a local run ever said so.

Two halves, and both are needed. CI has to be able to see the tags:

```yaml
    with:
      fetch-tags: true
```

The flag's own trap, recorded because it cost a red build within the
hour: the checkout depth must be written as a **quoted** `'0'`. GitHub
expressions treat the number `0` as falsy, so the usual
`condition && 0 || 1` ternary evaluates to `1` whatever the condition is
-- the checkout stays shallow, no tags arrive, and `fetch-tags: true`
does nothing while appearing to be set.

And the test must not be able to pass by finding nothing. A check that
returns early when its input is missing is not a check; where the input
is guaranteed — CI, with `fetch-tags` on — absence is a failure of the
setup and should be reported as one, not skipped. Otherwise the flag can
be dropped later and everything stays green.

### Moving `ci-vN` does not fix a run that already exists

A run resolves the workflow it calls when it is CREATED, and keeps that
commit. Re-running it re-runs the same commit -- the broken one -- so
moving the major tag does not rescue anything already on the board.

This cost real confusion during the Source Directory's adoption. The
sequence was:

1. A push run failed on the `fetch-tags` bug in ci-v1.2.0.
2. ci-v1.2.1 fixed it and `ci-v1` moved.
3. Runs created after the move passed.
4. Re-running the FAILED run reproduced the failure exactly, because it
   was still pinned to ci-v1.2.0 -- and that fresh failure became the
   newest result for its context, making the pull request look worse
   than before the clean-up.

What actually works:

- A run created after the tag moved. A new push, or a re-run of a run
  that was itself created after the move.
- For a pull request already carrying a failed context: a new commit.
  Every run on a commit contributes its contexts to that commit, and a
  failure from a run pinned to a broken workflow cannot be taken off it.
  Amending gives a new SHA with identical content, which is enough.

So: cut the fix, move the tag, and then push, rather than re-running
what is already red.

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

**Adoption.** datadesk, the Source Directory and the crawler all call
`python-checks.yml` and `conforms.yml` as of 5 September 2026. The plan
that sequenced it is `MizzouNewsCrawler/docs/BUILD_AND_CI_ARCHITECTURE.md`:
hash-keyed images first, then the base image's contents, then the
requirements files, then the shared workflows, then the enrichment split.
