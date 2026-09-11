"""Which county a place is in, and the rule for when it is in several.

WHY THIS IS SHARED AND NOT A FUNCTION IN EACH SERVICE

Every rung of the Census ladder except one can be read off the code
itself. A county GEOID begins with its state, a tract and a block begin
with their county, so the hierarchy needs no lookup:

    29151        Osage County, Missouri  = state 29 + county 151
    29151960100  a tract inside it       = starts with 29151

A place does not. `2938000` says state 29 and place 38000 and nothing
whatever about which county that is, because places are drawn by
municipal boundaries and counties are not. Kansas City is in four of
them. The only way to know is a table, and the table is not the hard
part -- the rule for reading it is.

That rule was written twice. The crawler resolved places at enrichment
time and the review console resolved them again at read time, each with
its own copy of the same file. Two implementations of one judgement call
is how two services come to disagree about which county a town is in,
and the disagreement surfaces as a number that does not reconcile rather
than as an error anybody can see.

THE MULTI-COUNTY RULE (decided 2026-09-11)

Of 32,188 places, 30,884 sit in one county. 1,199 span two, 87 span
three, 15 span four and 3 span five.

**The primary county wins, and the span is returned alongside so a
caller can tell the answer was a choice.** The primary is the Census's
own: the county the place is principally in.

Contributing every county a place touches was rejected. It would put
Cass, Clay, Jackson and Platte on any story that says "Kansas City", and
three of the four would be wrong about what the story is about. A wrong
county is worse than a missing one here, because a missing one is
visible as a gap and a wrong one reads as a finding.

The span is returned rather than discarded so the places where this is a
judgement call can be found again, and so a later decision to treat them
differently does not have to begin by identifying them. It is load-
bearing more often than 4% suggests: in a March 2026 Missouri run, 4,939
of 17,369 rollups were multi-county places -- 28% -- because the places
that get mentioned in news are the large ones that span counties.
"""

from __future__ import annotations

import json
from importlib import resources

__all__ = ["PLACE_COUNTY_COUNT", "county_for_place", "to_county"]

#: Places in the crosswalk. Asserted by the tests so a truncated or
#: swapped data file fails loudly rather than resolving fewer places.
PLACE_COUNTY_COUNT = 32188

_crosswalk: dict[str, list] | None = None


def _load() -> dict[str, list]:
    global _crosswalk
    if _crosswalk is None:
        raw = (
            resources.files("lnic_contracts")
            .joinpath("data/place_to_county.json")
            .read_text()
        )
        _crosswalk = json.loads(raw)
    return _crosswalk


def county_for_place(place_geoid: str | None) -> tuple[str | None, int]:
    """`(county GEOID, how many counties the place spans)`.

    `(None, 0)` where the place is not in the crosswalk -- a gap, never a
    guess. See the module docstring for why the primary county wins.
    """
    entry = _load().get((place_geoid or "").strip())
    return (entry[0], int(entry[1])) if entry else (None, 0)


def to_county(geoid: str | None, level: str | None) -> str | None:
    """County GEOID for any coding on the ladder, or None where undecidable.

    County, tract and block begin with state+county and are read off the
    code. A place goes through the crosswalk. A state coding has no
    county, and saying so is the point: a statewide story belongs to no
    county, and picking one for it would invent geography.
    """
    if not geoid:
        return None
    if level in ("county", "tract", "block"):
        return geoid[:5] if len(geoid) >= 5 else None
    if level == "place":
        return county_for_place(geoid)[0]
    return None
