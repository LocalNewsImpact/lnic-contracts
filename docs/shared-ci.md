# Shared build machinery

This repository holds two things for the suite: the shapes one service
writes and another reads, and the workflows that build and check them.

They are versioned separately, in one repository, under two tag series:

| Tag | What it versions | How a consumer pins it |
| --- | --- | --- |
| `v0.2.0` | the Python package | `lnic-contracts @ https://.../archive/refs/tags/v0.2.0.tar.gz` |
| `ci-v1` | the reusable workflows | `uses: LocalNewsImpact/lnic-contracts/.github/workflows/image-build.yml@ci-v1` |

Two series because the cadences differ. A workflow is edited often and
affects nothing at runtime; the package defines a shape two services must
agree on, and changing it strands data if they disagree. One tag series
for both would mean a CI tweak bumping the version of a data contract
that had not changed, and "what is in 0.3.0" would stop being answerable.

A workflow reference is a git ref, not a pip install, so pinning them
separately costs nothing.

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
