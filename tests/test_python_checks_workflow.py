"""A cache with nothing to save fails the job after the work passed.

`setup-python`'s post-step saves ~/.cache/pip. A repository whose
`install` runs inside a prebuilt image never writes that directory, so
on a cache MISS the save errors and the job goes red -- after lint or
the tests reported success. On a hit the restore creates the directory
and the save finds it, which is why this survived until the crawler's
cache entry was evicted and three green pull requests went red.

The caching is now the caller's to ask for. These read the workflow
text rather than the runner, because the runner is where it was
already too late.
"""

import re
from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github/workflows"
CALLED = ("python-checks.yml", "conforms.yml", "image-build.yml")

SETUP_PYTHON = re.compile(
    r"uses: actions/setup-python@[^\n]*\n(?P<body>(?:[ \t]+[^\n]*\n)+)"
)


def _text(name):
    return (WORKFLOWS / name).read_text()


def _cache_lines(name):
    return [
        line.strip()
        for match in SETUP_PYTHON.finditer(_text(name))
        for line in match.group("body").splitlines()
        if line.strip().startswith("cache:")
    ]


def test_the_caller_says_whether_to_cache():
    checks = _text("python-checks.yml")
    assert "pip-cache:" in checks, "no input for the caller to set"
    declaration = checks.split("pip-cache:", 1)[1].split("install:", 1)[0]
    assert "type: boolean" in declaration
    # On by default: every repository that installs on the runner keeps
    # the cache it has, so this release breaks no caller.
    assert "default: true" in declaration


def test_no_stage_caches_unconditionally():
    """The four stages are one edit apart and were four copies of the
    same line; a fifth stage copied from them must not reintroduce it."""
    unconditional = [
        line
        for line in _cache_lines("python-checks.yml")
        if "inputs.pip-cache" not in line
    ]
    assert unconditional == []


def test_every_stage_reads_the_input():
    lines = _cache_lines("python-checks.yml")
    assert len(lines) == 4, f"expected one per stage, found {lines}"
    for line in lines:
        assert line == "cache: ${{ inputs.pip-cache && 'pip' || '' }}"


@pytest.mark.parametrize("workflow", CALLED)
def test_a_called_workflow_caches_only_when_asked(workflow):
    """The rule is the file's, not python-checks.yml's. A cache added to
    any workflow a repository calls carries the same failure."""
    for line in _cache_lines(workflow):
        assert "inputs." in line, f"{workflow} caches without asking the caller"
