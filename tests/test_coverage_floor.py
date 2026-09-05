"""The floor, run rather than read.

Three repositories each enforced their own number and all three numbers
were wrong. What is tested here is the one that replaces them: that it
refuses under the floor, accepts at it, and -- the case a floor most
often gets wrong -- refuses to call an empty or missing report a pass.
"""

import io
import subprocess
import sys
from pathlib import Path

import pytest

from lnic_contracts import coverage_floor as cf

REPO_ROOT = Path(__file__).resolve().parents[1]


def _report(tmp_path, covered, valid, **extra):
    attrs = {
        "line-rate": f"{covered / valid:.4f}" if valid else "1",
        "lines-valid": str(valid),
        "lines-covered": str(covered),
    }
    attrs.update(extra)
    xml = tmp_path / "coverage.xml"
    body = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    xml.write_text(f'<?xml version="1.0" ?>\n<coverage {body}></coverage>\n')
    return xml


def _run(report):
    out = io.StringIO()
    return cf.check(report, out), out.getvalue()


# --- the floor itself ---------------------------------------------------------


def test_the_floor_is_eighty_percent():
    """The rule the suite agreed. Raising it is a decision made here, once."""
    assert cf.FLOOR == 80


def test_over_the_floor_passes(tmp_path):
    status, out = _run(_report(tmp_path, 870, 1000))
    assert status == 0
    assert "87.00%" in out and "floor is 80%" in out


def test_exactly_at_the_floor_passes(tmp_path):
    status, _ = _run(_report(tmp_path, 800, 1000))
    assert status == 0


def test_one_line_under_fails_and_says_how_many_lines_are_needed(tmp_path):
    status, out = _run(_report(tmp_path, 799, 1000))
    assert status == cf.UNDER
    assert "79.90%" in out
    assert "1 more line need" in out


def test_the_comparison_is_exact_not_rounded(tmp_path):
    """coverage.py's fail_under rounds to precision 0 first, so 79.5%
    passes an 80 there. 21,965 lines at 79.96% is 8 lines short, and it
    is short."""
    status, out = _run(_report(tmp_path, 17564, 21965))
    assert status == cf.UNDER
    assert "8 more lines" in out


# --- what is not a pass -------------------------------------------------------


def test_a_missing_report_is_not_measured(tmp_path):
    status, out = _run(tmp_path / "coverage.xml")
    assert status == cf.NOT_MEASURED
    assert "--cov-report=xml" in out


def test_a_report_of_zero_lines_is_not_measured(tmp_path):
    """`--cov` pointed at nothing measures nothing, and coverage.py calls
    that a line-rate of 1.0. It is not 100%."""
    status, out = _run(_report(tmp_path, 0, 0))
    assert status == cf.NOT_MEASURED
    assert "no lines" in out


def test_a_report_without_line_counts_is_not_measured(tmp_path):
    xml = tmp_path / "coverage.xml"
    xml.write_text('<coverage line-rate="0.9"></coverage>')
    status, out = _run(xml)
    assert status == cf.NOT_MEASURED
    assert "lines-valid" in out


def test_a_file_that_is_not_xml_is_not_measured(tmp_path):
    xml = tmp_path / "coverage.xml"
    xml.write_text("TOTAL 1000 130 87%\n")
    status, out = _run(xml)
    assert status == cf.NOT_MEASURED
    assert "not an XML" in out


# --- the entry points the repositories and the workflow use -------------------


def test_main_defaults_to_coverage_xml_in_the_working_directory(tmp_path, monkeypatch):
    _report(tmp_path, 900, 1000)
    monkeypatch.chdir(tmp_path)
    assert cf.main([]) == 0


def test_main_refuses_more_than_one_argument(capsys):
    assert cf.main(["a.xml", "b.xml"]) == 2
    assert "usage" in capsys.readouterr().out


@pytest.mark.parametrize(
    "invocation",
    [
        [sys.executable, "-m", "lnic_contracts.coverage_floor"],
        [
            sys.executable,
            str(REPO_ROOT / "src" / "lnic_contracts" / "coverage_floor.py"),
        ],
    ],
    ids=[
        "as a module, how a repository's make test runs it",
        "as a file, how the shared workflow runs it",
    ],
)
def test_runs_as_a_script_and_exits_with_the_verdict(tmp_path, invocation):
    report = _report(tmp_path, 700, 1000)
    result = subprocess.run(
        [*invocation, str(report)],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PYTHONPATH": str(REPO_ROOT / "src"), "PATH": ""},
    )
    assert result.returncode == cf.UNDER, result.stderr
    assert "under the suite's floor" in result.stdout


def test_the_shared_workflow_runs_this_floor_after_make_test():
    """The workflow is the other half of the rule: a repository's
    `make test` runs the floor locally, python-checks.yml runs the same
    file after `make test` in CI. If the step goes, so does the rule."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "python-checks.yml").read_text()
    test_job = workflow[
        workflow.index("\n  test:\n") : workflow.index("\n  integration:\n")
    ]
    make_test = test_job.index("run: make test")
    floor = test_job.index("coverage_floor.py")
    assert make_test < floor, "the floor must run after make test, on its report"
