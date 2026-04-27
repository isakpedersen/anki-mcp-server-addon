from typing import Any
import logging

from ....tool_decorator import Tool
from ....handler_wrappers import HandlerError, get_col

logger = logging.getLogger(__name__)

_EASE_NAMES = {
    1: "Again",
    2: "Hard",
    3: "Good",
    4: "Easy"
}

_TYPE_NAMES = {
    0: "learn",
    1: "review",
    2: "relearn",
    3: "filtered",
    4: "manual"
}

@Tool("get_review_history",
      "Get recent card review records from the review log. Returns actual reviews with card content, deck, rating, and time spent. "
      "Use limit to control how many to return (defualt 10, max 500). "
      "deck_name to filter on deck name (including subdecks), since_days to limit to the last N days, rating (1=Again, 2=Hard, 3=Good, 4=Easy) to filter by answer."
      "review_type to filter by type (0=learn, 1=review, 2=relearn, 3=filtered, 4=manual)",
)
def get_review_history(limit: int = 10, deck_name: str | None = None, since_days: int | None = None, rating: int | None = None, review_type: int | None = None) -> dict[str, Any]:
    if limit not in range(1, 501):
        raise HandlerError(
            "Limit out of bounds",
            hint="Limit must be between 1 and 500",
        )
    if rating is not None and rating not in range(1, 5):
        raise HandlerError(
            f"Invalid rating: {rating}",
            hint="Rating must be 1(again), 2(hard), 3(good), or 4(easy)",
        )
    
    if review_type is not None and review_type not in range(0,5):
        raise HandlerError(
            f"Invalid review type: {review_type}",
            hint="Review type must be 0(learn), 1(review), 2(relearn), 3(filtered), or 4(manual)"
        )

    col = get_col()

    conditions = []
    params = []

    if deck_name is not None:
        deck_ids = []
        for deck in col.decks.all_names_and_ids():
            if deck_name == deck.name or f"{deck_name}::" in deck.name:
                deck_ids.append(deck.id)
        if not deck_ids:
            raise HandlerError(
                "deck_name not found",
                hint="Use list_decks to see available decks",
            )
        conditions.append(f"c.did IN ({', '.join(['?' for _ in deck_ids])})")
        params.extend(deck_ids)

    if since_days is not None:
        day_cutoff = col.sched.day_cutoff
        cutoff_ms = (day_cutoff - 86400 * since_days) * 1000
        conditions.append("r.id >= ?")
        params.append(cutoff_ms)

    if rating is not None:
        conditions.append("r.ease = ?")
        params.append(rating)

    if review_type is not None:
        conditions.append("r.type = ?")
        params.append(review_type)


    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = col.db.all(
        f"""
        SELECT r.ease, n.flds, r.type
        FROM revlog r
        LEFT JOIN cards c ON r.cid = c.id
        LEFT JOIN notes n ON c.nid = n.id
        {where}
        ORDER BY r.id DESC
        LIMIT ?
        """,
        *params,
        limit,
    )
    
    reviews = []
    for row in rows:
        if row[1] is None:
            logger.debug("Note fields missing for card %s (note may be deleted)", row[0])
        reviews.append({
            "ease": _EASE_NAMES.get(row[0], f"unknown({row[0]})"),
            "fields": row[1].split("\x1f") if row[1] is not None else None,
            "type": _TYPE_NAMES.get(row[2], f"unknown({row[2]})"),
        })

    return {
        "reviews": reviews,
        "count": len(reviews),
    }

