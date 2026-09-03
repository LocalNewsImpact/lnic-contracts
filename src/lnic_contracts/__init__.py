"""Shapes one LNIC service writes and another reads.

Organised by the handover each shape describes, not by the service that
happens to write it, because the services are still moving. The crawler is
to be split into crawling/cleaning and analysis/enrichment, and the
`sources` table is to move to the source directory -- four or five services
where there were three, and each split turns an internal function call into
a handover with a shape.

    review_note   the crawler tells the review console it has held an
                  article, and what to restore if the hold is lifted

A shape belongs here when it crosses a service boundary. A shape with one
consumer is a module and belongs in that service.
"""

from lnic_contracts import review_note

__all__ = ["review_note", "__version__"]
__version__ = "0.1.0"
