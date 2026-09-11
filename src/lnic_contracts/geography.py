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

import csv
import json
import re
from importlib import resources

__all__ = [
    "PLACE_COUNTY_COUNT",
    "canonical_county",
    "canonical_place",
    "county_for_place",
    "state_code",
    "suggest_counties",
    "suggest_places",
    "to_county",
]

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


# --- names, and what to offer when one does not match ------------------------
#
# A typed place name is worth nothing until it resolves, and one that
# resolves to the WRONG place is worse than one that does not resolve at
# all. Both halves live here for the same reason the crosswalk does: the
# console suggests names and the crawler resolves them, and if those read
# different tables a reviewer can pick a suggestion that then fails, with
# no way to understand why.
#
# Two copies of `census_places.csv` existed before this -- one per
# repository -- which is exactly the arrangement `county_for_place`
# removed above.

#: LSAD descriptors the gazetteers append to a name, and the trailing
#: parenthetical that sits AFTER one. See `_bare` for why both.
_SUFFIX = re.compile(
    r"\s+(city|town|village|borough|cdp|municipality|comunidad|"
    r"zona urbana|urban county|metro government|metropolitan government|"
    r"unified government|consolidated government)$",
    re.IGNORECASE,
)
_COUNTY_SUFFIX = re.compile(
    r"\s+(county|parish|borough|census area|municipality|municipio|"
    r"city and borough|planning region|city)$",
    re.IGNORECASE,
)
_PAREN = re.compile(r"\s*\([^)]*\)\s*$")

_places: dict | None = None
_counties: dict | None = None


def _fold(name: str) -> str:
    """Lowercase, collapse whitespace, drop punctuation but keep an
    internal apostrophe -- "Lee's Summit" is one place, not two."""
    text = (name or "").strip().lower()
    text = re.sub(r"[^\w\s']", " ", text)
    return " ".join(text.split())


def _bare(name: str) -> str:
    """A gazetteer name without its type suffix.

    The parenthetical comes off FIRST: it sits after the descriptor, so
    `_SUFFIX` anchored to the end never matches
    "Nashville-Davidson metropolitan government (balance)" while it is
    there, and the whole legal name becomes the key.
    """
    return _SUFFIX.sub("", _PAREN.sub("", name or "")).strip()


def _load_names() -> tuple[dict, dict]:
    global _places, _counties
    if _places is None:
        places: dict[tuple[str, str], tuple[str, str]] = {}
        rows = (
            resources.files("lnic_contracts")
            .joinpath("data/census_places.csv")
            .read_text()
            .splitlines()
        )
        for row in csv.DictReader(rows):
            bare = _bare(row["NAME"])
            value = (row["GEOID"], bare)
            key = (row["USPS"], _fold(bare))
            # First wins on a tie, the same rule the crawler's gazetteer
            # has always used for two places sharing a bare name.
            places.setdefault(key, value)
            # A consolidated government is filed under its legal name and
            # written under a shorter one: nobody types "Lexington-
            # Fayette". Each half is registered, and first-wins keeps a
            # real place's name its own -- California has a Sunnyside, so
            # "Sunnyside-Tahoe City" does not get to claim it.
            if "-" in bare:
                for part in bare.split("-"):
                    if part.strip():
                        places.setdefault((row["USPS"], _fold(part)), value)
        counties: dict[tuple[str, str], tuple[str, str]] = {}
        rows = (
            resources.files("lnic_contracts")
            .joinpath("data/census_counties.csv")
            .read_text()
            .splitlines()
        )
        for row in csv.DictReader(rows):
            bare = _COUNTY_SUFFIX.sub("", row["NAME"]).strip()
            counties[(row["USPS"], _fold(bare))] = (row["GEOID"], bare)
        _places, _counties = places, counties
    return _places, _counties


def canonical_place(state: str, name: str) -> tuple[str | None, str | None]:
    """`(GEOID, the gazetteer's own spelling)` for a place, or `(None, None)`.

    The canonical name is what a normalisation pass should write back --
    "St. Louis", not "saint louis".
    """
    places, _ = _load_names()
    hit = places.get((state_code(state) or "", _fold(name)))
    return hit if hit else (None, None)


def canonical_county(state: str, name: str) -> tuple[str | None, str | None]:
    """`(GEOID, the gazetteer's own spelling)` for a county."""
    _, counties = _load_names()
    hit = counties.get((state_code(state) or "", _fold(name)))
    return hit if hit else (None, None)


def _suggest(table: dict, name: str, prefer_state: str | None, limit: int):
    """Close names, the preferred state's first.

    RANKED, NEVER FILTERED (decided 2026-09-11).

    Ranking catches the error the pipeline actually made: a story about
    the sewer trustees of Freeburg, a village in Osage County, Missouri,
    was extracted as "Freeburg, IL". Illinois genuinely has a Freeburg,
    the lookup succeeded, and the story was filed three hundred miles
    away -- nothing downstream could catch it, because the answer was
    internally valid. Somebody typing "Freeburg" while working a Missouri
    outlet is offered Missouri's first.

    Filtering to the preferred state would be wrong, and one month of one
    corpus proves it: Whiteman Air Force Base, Nashville, Wichita State,
    the University of Pittsburgh and Seattle were all covered by Missouri
    outlets. A Missouri-only list makes real coverage unenterable, which
    is how a queue teaches people to work around it.
    """
    import difflib

    want = _fold(name)
    if not want:
        return []
    prefer = state_code(prefer_state) if prefer_state else None
    pool = {key[1] for key in table}
    close = difflib.get_close_matches(want, pool, n=limit * 6, cutoff=0.72)
    # `get_close_matches` returns its results BEST FIRST, and that order
    # is the whole value of it. Sorting the output by name afterwards
    # threw it away: "Nashvile" returned Asherville and Asheville and not
    # Nashville at all, because the alphabet does not know which is
    # closer. The position is kept and sorted on.
    rank = {folded: i for i, folded in enumerate(close)}

    out, seen = [], set()
    for folded in close:
        for (usps, key), (geoid, official) in table.items():
            if key != folded or geoid in seen:
                continue
            seen.add(geoid)
            out.append(
                {
                    "geoid": geoid,
                    "name": official,
                    "state": usps,
                    "exact": key == want,
                    "_rank": rank[folded],
                }
            )
    # Exact first, then the preferred state, then how close it is.
    out.sort(
        key=lambda row: (
            not row["exact"],
            prefer is not None and row["state"] != prefer,
            row["_rank"],
            row["name"],
        )
    )
    return [{k: v for k, v in row.items() if k != "_rank"} for row in out[:limit]]


def suggest_places(name: str, prefer_state: str | None = None, limit: int = 8):
    """Places close to what was typed, the preferred state's first."""
    places, _ = _load_names()
    return _suggest(places, name, prefer_state, limit)


def suggest_counties(name: str, prefer_state: str | None = None, limit: int = 8):
    """Counties close to what was typed, the preferred state's first."""
    _, counties = _load_names()
    return _suggest(counties, name, prefer_state, limit)


# Source records carry a state as "MO" or "Missouri" depending on when
# they were loaded, so every lookup normalises first.
_STATE_BY_NAME = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT",
    "delaware": "DE", "district of columbia": "DC", "florida": "FL",
    "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY",
    "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT",
    "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "puerto rico": "PR", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


def state_code(value: str | None) -> str | None:
    """`"MO"` for "MO", "mo" or "Missouri"; None for anything else."""
    text = (value or "").strip()
    if len(text) == 2 and text.upper() in set(_STATE_BY_NAME.values()):
        return text.upper()
    return _STATE_BY_NAME.get(text.lower())
