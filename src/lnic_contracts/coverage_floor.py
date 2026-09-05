"""The suite's coverage floor, in one place.

Every repository measured coverage and the rule was 80 percent. What the
repositories enforced was something else: the crawler said 78 in two
files, the Source Directory said 78 in one, datadesk said nothing and
did not measure. Nothing held the four to one number, so they drifted,
and the drift was invisible because each repository was green against
itself.

This module is the number. The shared workflow runs it after `make test`
in CI, and each repository's `make test` runs it locally, on the same
report -- coverage.xml, which pytest-cov writes with --cov-report=xml --
so the hook and CI cannot disagree. A repository carries no floor of its
own (conforms.yml refuses a `fail_under`), so the only way to change what
CI accepts is to change it here, for every repository at once.

    python -m lnic_contracts.coverage_floor [coverage.xml]

Exit 0 at or over the floor, 1 under it, 2 when nothing was measured.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TextIO

FLOOR = 80  # percent of lines, across the suite; it only goes up

UNDER = 1
NOT_MEASURED = 2


def check(report: Path, out: TextIO = sys.stdout) -> int:
    """Compare the line coverage in a coverage.py XML report to FLOOR.

    Compared exactly, not rounded: 79.96% is under 80%. coverage.py's own
    `fail_under` rounds the total to its `precision` first, which is 0 by
    default, so 79.5% passes a fail_under of 80 there. One rule, no
    rounding.
    """
    try:
        root = ET.parse(report).getroot()
    except FileNotFoundError:
        print(
            f"{report}: not found. `make test` must write it: "
            "pytest --cov --cov-report=xml",
            file=out,
        )
        return NOT_MEASURED
    except ET.ParseError as exc:
        print(f"{report}: not an XML coverage report ({exc})", file=out)
        return NOT_MEASURED

    try:
        valid = int(root.attrib["lines-valid"])
        covered = int(root.attrib["lines-covered"])
    except (KeyError, ValueError):
        print(
            f"{report}: no lines-valid / lines-covered on the root element; "
            "is this coverage.py's XML report?",
            file=out,
        )
        return NOT_MEASURED

    # A report of nothing is not 100%. `--cov` pointed at a package that
    # does not exist, or at a directory the tests never import, measures
    # zero lines and coverage.py reports that as a rate of 1.0.
    if valid == 0:
        print(f"{report}: measured no lines; is --cov pointed at the code?", file=out)
        return NOT_MEASURED

    percent = 100 * covered / valid
    if covered * 100 < FLOOR * valid:
        # Integer arithmetic, so the count is exact: -(-a // b) is ceil.
        needed = -(-FLOOR * valid // 100) - covered
        print(
            f"coverage {percent:.2f}% ({covered:,} of {valid:,} lines) is under "
            f"the suite's floor of {FLOOR}%: {needed:,} more line"
            f"{'s' if needed != 1 else ''} need a test",
            file=out,
        )
        return UNDER

    print(
        f"coverage {percent:.2f}% ({covered:,} of {valid:,} lines); "
        f"the suite's floor is {FLOOR}%",
        file=out,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) > 1:
        print("usage: python -m lnic_contracts.coverage_floor [coverage.xml]")
        return 2
    return check(Path(args[0]) if args else Path("coverage.xml"))


if __name__ == "__main__":
    sys.exit(main())
