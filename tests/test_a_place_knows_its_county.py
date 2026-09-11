"""A place GEOID does not carry its county, and two services were each
deciding what to do about that on their own."""

from lnic_contracts.geography import (
    PLACE_COUNTY_COUNT,
    county_for_place,
    to_county,
)


def test_every_other_rung_is_readable_from_the_code():
    """This is why places need a table and nothing else does. State
    prefixes county; county prefixes tract and block. The hierarchy is
    declared by the digits."""
    assert to_county("29151", "county") == "29151"
    assert to_county("29151960100", "tract") == "29151"
    assert to_county("291519601001000", "block") == "29151"


def test_a_place_geoid_says_nothing_about_its_county():
    """2938000 is state 29, place 38000. Jackson County is 29095, and
    nothing in the place code points at it."""
    assert to_county("2938000", "place") == "29095"
    assert not "2938000".startswith("29095")


def test_a_place_in_several_counties_takes_its_primary_one():
    """Kansas City is in four. Contributing all four would put Cass, Clay
    and Platte on any story that says "Kansas City", and three would be
    wrong about what the story is about.

    The span comes back so a caller can tell the answer was a choice."""
    county, span = county_for_place("2938000")
    assert county == "29095"
    assert span == 4


def test_the_ordinary_case_reports_its_span_too():
    """So a caller never has to special-case the shape."""
    assert county_for_place("0100100") == ("01017", 1)


def test_a_place_outside_the_crosswalk_is_a_gap_not_a_guess():
    assert county_for_place("9999999") == (None, 0)
    assert county_for_place(None) == (None, 0)
    assert county_for_place("") == (None, 0)
    assert to_county("9999999", "place") is None


def test_a_statewide_coding_belongs_to_no_county():
    """Picking one for it would invent geography."""
    assert to_county("29", "state") is None
    assert to_county("29", None) is None
    assert to_county(None, "county") is None


def test_the_crosswalk_is_whole():
    """A truncated or swapped data file resolves fewer places and raises
    nothing. The count is asserted so that fails here instead of showing
    up as counties quietly going missing from a map."""
    from lnic_contracts.geography import _load

    assert len(_load()) == PLACE_COUNTY_COUNT


def test_the_span_distribution_is_what_the_rule_was_written_for():
    """The rule is load-bearing for about 4% of places. Recorded here so
    a data refresh that changes the shape of the problem is visible."""
    from collections import Counter

    from lnic_contracts.geography import _load

    spans = Counter(int(v[1]) for v in _load().values())
    assert spans[1] == 30884
    assert sum(n for span, n in spans.items() if span > 1) == 1304
    assert max(spans) == 5


# --- what a person may type, and what comes back ------------------------------


def test_a_name_resolves_to_the_gazetteers_own_spelling():
    """The canonical name is what a normalisation pass writes back."""
    from lnic_contracts.geography import canonical_county, canonical_place

    assert canonical_place("MO", "Linn") == ("2943238", "Linn")
    assert canonical_county("MO", "Osage") == ("29151", "Osage")
    # A state may arrive spelled out: records carry both.
    assert canonical_county("Missouri", "Osage")[0] == "29151"
    # And a consolidated government resolves under the name people use.
    assert canonical_place("KY", "Lexington")[0] == "2146027"


def test_the_preferred_state_is_ranked_first_and_not_filtered():
    """RANKED, NEVER FILTERED.

    A story about the sewer trustees of Freeburg -- a village in Osage
    County, Missouri -- was extracted as "Freeburg, IL". Illinois has a
    Freeburg, the lookup succeeded, and the story was filed three hundred
    miles away; nothing downstream could catch it, because the answer was
    internally valid. Somebody typing "Freeburg" for a Missouri outlet is
    offered Missouri's first.

    Filtering would be wrong: Whiteman Air Force Base, Nashville, Wichita
    State, the University of Pittsburgh and Seattle were all covered by
    Missouri outlets in one month, and a Missouri-only list makes real
    coverage unenterable.
    """
    from lnic_contracts.geography import suggest_places

    hits = suggest_places("Freeburg", prefer_state="MO", limit=5)
    assert hits[0]["state"] == "MO"
    assert "IL" in {h["state"] for h in hits}, "the other states are still offered"


def test_a_typo_is_offered_a_correction():
    """Suggestions exist so a near miss is corrected rather than refused."""
    from lnic_contracts.geography import suggest_places

    hits = suggest_places("Westphalya", prefer_state="MO", limit=3)
    assert hits[0]["name"] == "Westphalia"
    assert hits[0]["state"] == "MO"
    assert hits[0]["exact"] is False


def test_closeness_survives_the_sort():
    """`get_close_matches` returns its results best-first and that order
    is the value of it. Sorting the output by name afterwards threw it
    away: "Nashvile" returned Asherville and Asheville and not Nashville
    at all, because the alphabet does not know which is closer."""
    from lnic_contracts.geography import suggest_places

    assert suggest_places("Nashvile", limit=3)[0]["name"] == "Nashville"


def test_a_state_is_read_however_it_is_written():
    from lnic_contracts.geography import state_code

    assert state_code("MO") == state_code("mo") == state_code("Missouri") == "MO"
    assert state_code("") is None
    assert state_code("Freedonia") is None
