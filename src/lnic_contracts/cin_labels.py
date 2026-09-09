"""The ten Critical Information Needs categories, and their order.

WHY THIS IS SHARED AND NOT A CONSTANT IN EACH SERVICE
The crawler classifies articles into these ten; the review console shows
them to a coder and stores what the coder picked; the labels are then
compared as strings against `articles.primary_label`. Three services,
one vocabulary, and a rename in one of them is a silent mismatch in the
others -- every comparison misses, agreement collapses, and nothing
points at the cause.

THE ORDER IS LOAD-BEARING. DO NOT SORT THIS.
The crawler builds the model's label map by position:

    label2id = {label: idx for idx, label in enumerate(LABELS)}

so index 0 is "Civic Life" because that is what index 0 meant when the
checkpoint was trained. Reordering this tuple does not raise, does not
fail a build, and silently relabels every prediction the model makes --
Sports arriving as Health, and no error anywhere.

A new category is therefore appended, never inserted, and only ever
alongside a retrained checkpoint that agrees with it.

SPELLING IS LOAD-BEARING TOO
`Civic information` carries a lowercase `i` and `Political life` a
lowercase `l`, because that is how the model emits them and how they sit
in `articles.primary_label`. They are not typos and correcting them
would break the comparison they exist for.
"""

from __future__ import annotations

#: The ten, in the order the model's label map is built from.
#: Index is the model's class id. See the module docstring before
#: touching the order.
LABELS: tuple[str, ...] = (
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

#: The order the codebook introduces them in, which is the order a
#: person reads them in and a reasonable one to render a list in.
#:
#: Separate from LABELS on purpose: a display order that could be
#: mistaken for the model's order is how somebody eventually "tidies"
#: the wrong one.
CODEBOOK_ORDER: tuple[str, ...] = (
    "Emergencies and Public Safety",
    "Health",
    "Education",
    "Transportation Systems",
    "Environment and Planning",
    "Economic Development",
    "Civic information",
    "Political life",
    "Sports",
    "Civic Life",
)


def label_for(class_id: int) -> str:
    """The label the model's output index means."""
    return LABELS[class_id]


def class_id_for(label: str) -> int:
    """The model's output index for this label.

    Raises rather than returning a sentinel: a label the model does not
    know is a bug in the caller, and -1 would be stored as a class id.
    """
    return LABELS.index(label)


def is_known(label) -> bool:
    """Whether this is one of the ten, exactly as the model spells it."""
    return isinstance(label, str) and label in set(LABELS)
