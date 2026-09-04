"""Does the built package carry the code, or only the version number?

datadesk's image reported lnic-contracts 0.2.0 and carried v0.1.0's code.
`/review/queue/` raised AttributeError on submit for a function that was
in the version the metadata claimed, and nothing anywhere noticed: every
test in every repository runs against a working tree, and the built
package is what consumers install.

Run against an interpreter that has the built sdist installed, from a
directory that is not the source tree -- otherwise `src/` is importable
and this proves nothing.
"""

import sys
from importlib import metadata
from pathlib import Path

# What a consumer imports. A name here that packaging drops is a runtime
# AttributeError in another repository.
PUBLIC = (
    "build",
    "read",
    "is_readable",
    "from_metadata",
    "into_metadata",
    "question",
    "build_decision",
    "record_decision",
    "decision_for",
    "is_answered",
)


def main() -> int:
    from lnic_contracts import review_note

    where = Path(review_note.__file__).resolve()
    if (Path.cwd() / "src") in where.parents:
        print(f"importing the source tree, not the package: {where}", file=sys.stderr)
        return 1

    version = metadata.version("lnic-contracts")
    missing = [name for name in PUBLIC if not hasattr(review_note, name)]
    if missing:
        print(
            f"lnic-contracts {version} packaged without: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    print(f"lnic-contracts {version}: {len(PUBLIC)} public names, all packaged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
