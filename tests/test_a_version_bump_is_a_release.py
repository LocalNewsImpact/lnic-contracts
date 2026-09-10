"""The tag has to follow the version without anybody remembering.

`pyproject.toml` said 0.4.0 and there was no `v0.4.0` tag. Consumers
install from `archive/refs/tags/v<version>.tar.gz`, so that version was
released in name only: nothing could install it, and the repository said
it had shipped something it had not. The bump was in the pull request and
the tag was a thing somebody was meant to do afterwards.

These hold the workflow to the properties that make it safe to leave
alone.

Read as text, not parsed. `test_python_checks_workflow.py` does the same
and for the same reason: this package is installed by two applications
and a test dependency here is a dependency there. PyYAML to assert that a
workflow says "main" is not worth that.
"""

import re
from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github/workflows/release-package.yml"
)
TEXT = WORKFLOW.read_text()

#: Each `- name:` step, with everything under it, in file order.
STEPS = re.split(r"\n      - (?:name|uses):", TEXT)[1:]


def _step(fragment):
    """The steps whose body mentions this."""
    return [s for s in STEPS if fragment in s]


def test_it_fires_when_the_version_changes():
    """The version lives in pyproject, so a release can only follow it."""
    trigger = TEXT.split("jobs:")[0]
    assert "branches: [main]" in trigger
    assert 'paths: ["pyproject.toml"]' in trigger


def test_the_checks_run_before_the_tag():
    """Two applications pin by tag. A tag pointing at something red is
    installed by both before anyone notices -- including by the pull
    request that would fix it."""
    checks = TEXT.index("Everything this repository checks")
    tagged = TEXT.index("- name: Tag it")
    assert checks < tagged, "the tag is written before the checks run"


def test_an_existing_tag_is_never_moved():
    """A tag consumers may already have installed must not come to mean
    something else."""
    tagging = _step("git tag ")
    assert tagging, "nothing tags anything"
    for step in tagging:
        assert "git tag -f" not in step, step
        assert "push -f" not in step, step
        assert "--force" not in step, step


def test_an_ordinary_merge_is_not_a_failure():
    """Most merges do not bump the version. A workflow that goes red on
    the ordinary case is one whose red runs nobody reads."""
    assert _step("already exists"), "nothing checks whether the tag is there"
    # Skipped, not failed: the work is conditional on the check.
    assert TEXT.count("if: steps.already.outputs.release == 'yes'") >= 3


def test_the_release_says_how_to_install_it():
    """The tarball URL is the whole interface. A release note without it
    makes every consumer work out the same line."""
    assert _step("archive/refs/tags"), "the release does not say how to install"


def test_it_is_not_the_shared_ci_tag():
    """`v1.2.3` is this package; `ci-v1.2.3` is the workflow three
    repositories call. A workflow that tagged one as the other would move
    a tag three repositories pin."""
    for step in _step("git tag "):
        assert "ci-v" not in step, step
    assert "group: release-package" in TEXT


def test_the_version_is_read_from_pyproject_and_not_typed():
    """A version written into the workflow is a second place to bump, and
    the whole fault here was a version recorded in two places falling out
    of step."""
    reading = _step("tomllib")
    assert reading, "the version is not read from pyproject"


# ------------------------------------------------- and the consumers follow

STEPS_TEXT = TEXT[TEXT.index("bump-consumers:") :]


def test_the_release_opens_the_consumers_pin_bump():
    """Tagging published nothing to anybody.

    Both consumers pin the tarball by tag, so until their requirements
    line changes they go on installing the old version. v0.5.0 and
    v0.6.0 each needed a hand-written pull request in two repositories.
    """
    assert "LocalNewsImpact/datadesk" in STEPS_TEXT
    assert "LocalNewsImpact/MizzouNewsCrawler" in STEPS_TEXT
    # Where each of them keeps the pin.
    assert "requirements.txt" in STEPS_TEXT
    assert "requirements-base.txt" in STEPS_TEXT


def test_the_checks_are_waited_for_before_it_lands():
    """The consumer's own CI is the gate, and the gate has to be shut
    before the merge, not after.

    This test used to assert that nothing merged at all. That was the
    right property when a person clicked approve; now the workflow
    lands the bump itself, and the property worth holding is that it
    cannot land one that has not gone green. `--watch` blocks until
    every required check has reported and exits non-zero if any failed.
    """
    assert "gh pr create" in STEPS_TEXT
    waited = STEPS_TEXT.index("gh pr checks")
    landed = STEPS_TEXT.index("gh pr merge")
    assert waited < landed, "it merges before waiting for the checks"
    assert "--watch" in STEPS_TEXT
    assert "--fail-fast" in STEPS_TEXT


def test_a_red_run_is_left_for_a_person():
    """Failing checks are a judgement call, which is exactly what this
    is not allowed to make. It stops and says so."""
    assert "checks failed" in STEPS_TEXT
    assert "left open for a person" in STEPS_TEXT


def test_a_missing_token_does_not_fail_the_release():
    """The release already happened. Failing it because nobody has made a
    cross-repository token would be a worse outcome than a pin somebody
    bumps by hand."""
    assert "CONSUMER_PR_TOKEN" in STEPS_TEXT
    assert "continue-on-error: true" in STEPS_TEXT
    assert "::warning::" in STEPS_TEXT


def test_it_does_not_stack_a_second_bump():
    """One open pull request per repository is this project's rule: every
    merge re-runs CI on all the others."""
    assert "deps/lnic-contracts-" in STEPS_TEXT
    assert "already has an open lnic-contracts bump" in STEPS_TEXT


def test_the_rewrite_is_python_and_not_sed():
    """`sed -i` takes a backup suffix on BSD and not on GNU, and the pin
    is a URL full of characters a regex and a shell each want to read.
    This has to be right the first time it runs unattended, so it is
    written in a form that can be run on a laptop exactly as it runs on
    the runner."""
    # The lines that run, not the ones that explain: the comment above
    # says `sed -i`, and an assertion that reads it is asserting about a
    # comment. The same slip cost a rewrite two files ago.
    running = [
        line
        for line in STEPS_TEXT.split("\n")
        if line.strip() and not line.strip().startswith("#")
    ]
    assert not [line for line in running if "sed -i" in line], running
    assert any("python3 -" in line for line in running)
    # The guard that stops it committing something unexpected.
    assert any("expected one pin" in line for line in running)


def test_the_heredoc_terminator_survives_the_yaml_block():
    """Indented, it is not a terminator and the script runs as one line;
    at column zero it is not inside the block scalar and the YAML will
    not parse. This repository has been bitten by the first and the
    second in the same file."""
    for line in TEXT.split("\n"):
        if line.strip() == "PYEOF":
            assert line.startswith("          "), repr(line)
            break
    else:
        raise AssertionError("no PYEOF terminator found")


def test_it_waits_for_a_check_to_exist_before_waiting_for_it_to_pass():
    """`gh pr checks` on a branch pushed a second ago reports "no checks
    reported" and exits NON-ZERO, which is indistinguishable from a red
    run.

    v0.8.0 lost that race in both consumers -- opened at 01:02:25, "no
    checks reported" at 01:02:26, both pull requests left open with
    nothing ever coming back to them, while the release run reported
    success. The wait has to be for registration first, then for the
    verdict.
    """
    # The lines that run, not the ones that explain. The comment above
    # this fix contains the string `--watch`, and an assertion reading it
    # would compare against prose -- which is the slip
    # `test_the_rewrite_is_python_and_not_sed` was written about, made
    # again here on the first attempt.
    running = "\n".join(
        line
        for line in STEPS_TEXT.split("\n")
        if line.strip() and not line.strip().startswith("#")
    )
    registering = running.index("REGISTERED=")
    watching = running.index("--watch")
    assert registering < watching, "it watches before any check exists"
    # Bounded: a consumer with genuinely no CI must not hang the job.
    assert "registered no checks" in STEPS_TEXT


def test_every_outcome_reaches_the_run_page():
    """This job is `continue-on-error`, so a release whose consumer half
    did nothing still reports success -- which is how v0.8.0 looked green
    while publishing to nobody. Each path says what it did."""
    assert STEPS_TEXT.count("GITHUB_STEP_SUMMARY") >= 3
    for outcome in ("landed", "checks failed", "no checks started"):
        assert outcome in STEPS_TEXT, outcome
