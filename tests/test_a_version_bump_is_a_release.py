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
