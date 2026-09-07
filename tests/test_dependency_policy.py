"""One dependency policy, in one file, for four repositories.

Dependabot has no shared configuration: `.github/dependabot.yml` is
per-repository and nothing inherits it, so a decision about how the
suite takes updates had to be made four times and drifted immediately.
Two repositories had a config at all; the other two took no version
updates whatever.

Renovate resolves `extends` across repositories, so every repository
here carries two lines pointing at `default.json` in this one, and the
policy below is the only place it is written down.

These read the preset as data rather than trusting a comment, because
the failure they guard against is silent: a preset that parses but says
something other than what was agreed still runs, every month, on four
repositories at once.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PRESET = json.loads((ROOT / "default.json").read_text())
OWN = json.loads((ROOT / "renovate.json").read_text())


def _rule(update_type):
    """The packageRule covering an update type."""
    for rule in PRESET["packageRules"]:
        if update_type in rule.get("matchUpdateTypes", []):
            return rule
    raise AssertionError(f"no rule covers {update_type!r}")


def test_updates_arrive_once_a_month():
    """The whole point of the arrangement: one decision, on a date
    somebody can plan around, not four repositories on four clocks."""
    assert PRESET["schedule"] == ["* 0-6 1 * *"]
    assert PRESET["timezone"] == "America/Chicago"


def test_everything_routine_arrives_as_one_pull_request():
    rule = _rule("patch")
    assert rule["groupName"] == "all non-major dependencies"
    for update_type in ("minor", "pin", "digest"):
        assert _rule(update_type) is rule


def test_a_major_is_not_swept_into_that_group():
    """actions/checkout 4 to 7 crossed a Node runtime. A major hidden in
    a group of forty is a major nobody read."""
    rule = _rule("major")
    assert "groupName" not in rule
    assert rule["dependencyDashboardApproval"] is True


def test_a_security_fix_does_not_wait_for_the_first_of_the_month():
    alerts = PRESET["vulnerabilityAlerts"]
    assert alerts["schedule"] == ["at any time"]
    assert alerts["groupName"] is None
    # The monthly hold-back must not apply either, or the fix waits.
    assert alerts["minimumReleaseAge"] is None
    assert PRESET["osvVulnerabilityAlerts"] is True


def test_a_stale_branch_rebases_itself():
    """Both open Dependabot pull requests sat BEHIND and could not merge
    without a human rebasing them."""
    assert PRESET["rebaseWhen"] == "behind-base-branch"


def test_nothing_merges_itself():
    """Renovate's recommended config does not automerge, and this does
    not add it: the suite deploys on merge to main."""
    assert "automerge" not in PRESET
    assert not any(r.get("automerge") for r in PRESET["packageRules"])


def test_this_repository_extends_the_preset_like_every_other():
    """The preset governs this repository too. A policy its own author
    is exempt from is a policy that goes untested."""
    assert OWN["extends"] == ["local>LocalNewsImpact/lnic-contracts"]
    assert set(OWN) <= {"$schema", "extends"}


@pytest.mark.parametrize("key", ["description"])
def test_each_rule_says_why(key):
    """Read by whoever is deciding whether to widen or narrow it."""
    assert PRESET[key]
    for rule in PRESET["packageRules"]:
        assert rule.get(key), rule
    assert PRESET["vulnerabilityAlerts"][key]
