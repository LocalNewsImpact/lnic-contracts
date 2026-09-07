# How the suite takes dependency updates

One policy, in one file, for four repositories.

## Why it is not Dependabot

`.github/dependabot.yml` is per-repository and nothing inherits it.
GitHub has no organisation-level configuration for version updates, so
"how does this suite take updates" had to be answered separately in every
repository, and the answers drifted:

| Repository | Before |
| --- | --- |
| `MizzouNewsCrawler` | twelve ecosystems, monthly, grouped |
| `NewsSourceDirectory` | four ecosystems, monthly on a Monday, grouped |
| `datadesk` | no version updates at all |
| `lnic-contracts` | no version updates at all |

Two repositories took no version updates whatever. The two that did ran
on separate clocks, so a decision about the suite was made twice, weeks
apart, with no view of the whole.

Renovate resolves `extends` across repositories. Every repository carries
the same two lines:

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["local>LocalNewsImpact/lnic-contracts"]
}
```

and the policy lives in `default.json` here. Changing the cadence, the
grouping or the hold-back is one commit to one file, and every repository
follows on its next run.

## What the policy says

**Routine updates arrive once a month**, in the early hours of the first,
Central time. Minor, patch, pin and digest updates are one pull request
per repository — the group is named `all non-major dependencies`. The
alternative is what `NewsSourceDirectory` saw on its first run: twelve
pull requests, twelve CI runs and twelve merges to move about forty
lines.

**A major update is not swept into that group.** It waits on the
dependency dashboard until somebody approves it, and then arrives on its
own. `actions/checkout` 4 to 7 is the case that argues for this: it
crosses a Node runtime, and a major buried in a group of forty is a
major nobody read.

**A security fix does not wait.** `vulnerabilityAlerts` overrides the
schedule, the grouping and the hold-back, so an advisory arrives
immediately and by itself. OSV alerts are on, which covers the Python
packages GitHub's own advisory database is thin on.

**Nothing merges itself.** Every repository in the suite deploys on merge
to `main`, so a merge is a deploy and a person makes it.

**A stale branch rebases itself** (`rebaseWhen: behind-base-branch`).
Both Dependabot pull requests open when this was written sat `BEHIND` and
could not merge without somebody rebasing them by hand.

**A release must be three days old** before it is proposed
(`minimumReleaseAge`), which is long enough for a yanked release to be
yanked.

## The dashboard

`dependencyDashboard` is on, so each repository has one issue listing
everything Renovate can see: what is scheduled, what is waiting on
approval, and what has been ignored. It is the closest thing to a single
view of the suite's dependency state, and it is where a major is
approved.

## Adding a repository

Add the two-line `renovate.json`, and nothing else. A repository that
needs an exception should get it here, as a `packageRule` with a
`description` saying why — not as local configuration, which is the
arrangement this replaced.
