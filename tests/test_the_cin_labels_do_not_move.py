"""The ten categories, pinned.

The order builds the model's label map by position --
`label2id = {label: idx for idx, label in enumerate(LABELS)}` -- so
index 0 is "Civic Life" because that is what index 0 meant when the
checkpoint was trained. Reordering does not raise, does not fail a
build, and silently relabels every prediction: Sports arriving as
Health, with no error anywhere.

So the order is written out here in full. Changing it means editing this
test deliberately, next to a retrained checkpoint that agrees.
"""

import pytest

from lnic_contracts import cin_labels


def test_the_order_is_the_models_class_ids():
    """Written out rather than sorted or derived. This is the assertion
    that makes a reorder a deliberate act."""
    assert cin_labels.LABELS == (
        "Civic Life",
        "Civic information",
        "Emergencies and Public Safety",
        "Health",
        "Transportation Systems",
        "Sports",
        "Environment and Planning",
        "Education",
        "Political life",
        "Economic Development",
    )


def test_there_are_ten():
    assert len(cin_labels.LABELS) == 10
    assert len(set(cin_labels.LABELS)) == 10


def test_the_spellings_are_the_models_own():
    """`Civic information` has a lowercase i and `Political life` a
    lowercase l, because that is how the model emits them and how they
    sit in `articles.primary_label`. Correcting them would break the
    string comparison they exist for."""
    assert "Civic information" in cin_labels.LABELS
    assert "Civic Information" not in cin_labels.LABELS
    assert "Political life" in cin_labels.LABELS
    assert "Political Life" not in cin_labels.LABELS


def test_the_class_id_round_trips():
    for expected, label in enumerate(cin_labels.LABELS):
        assert cin_labels.class_id_for(label) == expected
        assert cin_labels.label_for(expected) == label


def test_an_unknown_label_raises_rather_than_returning_a_sentinel():
    """-1 would be stored as a class id and read back as the last
    category."""
    with pytest.raises(ValueError):
        cin_labels.class_id_for("Weather")


@pytest.mark.parametrize("value", [None, "", "weather", "Civic Information", 3])
def test_is_known_is_exact(value):
    assert not cin_labels.is_known(value)


def test_the_codebook_order_is_the_same_ten():
    """A different order for reading, not a different vocabulary. If
    these ever diverge in membership, one of them is wrong."""
    assert set(cin_labels.CODEBOOK_ORDER) == set(cin_labels.LABELS)
    assert len(cin_labels.CODEBOOK_ORDER) == len(cin_labels.LABELS)


def test_the_two_orders_are_not_the_same_object():
    """Kept apart so a display order cannot be mistaken for the model's,
    which is how somebody eventually tidies the wrong one."""
    assert cin_labels.CODEBOOK_ORDER != cin_labels.LABELS
