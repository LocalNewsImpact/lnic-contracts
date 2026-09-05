"""Shapes one LNIC service writes and another reads.

Organised by the handover each shape describes, not by the service that
happens to write it, because the services are still moving. The crawler is
to be split into crawling/cleaning and analysis/enrichment, and the
`sources` table is to move to the source directory -- four or five services
where there were three, and each split turns an internal function call into
a handover with a shape.

    review_note   the crawler tells the review console it has held an
                  article, and what to restore if the hold is lifted

One thing here is not a shape: coverage_floor, the suite's 80 percent,
which every repository's `make test` and the shared CI workflow both
run. It lives in the package because that is what every repository
already installs, and a rule each repository restates is a rule that
drifts.

A shape belongs here when it crosses a service boundary. A shape with one
consumer is a module and belongs in that service.
"""

from importlib.metadata import PackageNotFoundError, version

from lnic_contracts import review_note

__all__ = ["__version__", "review_note"]

# Read from the installed package rather than restated here. It was
# restated, and said 0.1.0 while pyproject said 0.2.0 -- a third place a
# version lives, stale, in the repository whose whole point is that two
# services agree about one thing.
try:
    __version__ = version("lnic-contracts")
except PackageNotFoundError:  # running from a source tree, uninstalled
    __version__ = "0+unknown"
