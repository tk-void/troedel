"""What selling has brought in: takings, sales, what is still out there.

Computed from the list of items, no table of its own. For a few hundred
items that is faster than keeping sums up to date.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

MONTHS = 6


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _time(iso: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(iso) if iso else None
    except ValueError:
        return None


def compute(items: list[dict[str, Any]], today: datetime | None = None) -> dict[str, Any]:
    today = today or datetime.now().astimezone()
    sold = [i for i in items if i["status"] == "sold"]
    sold.sort(key=lambda i: i.get("sold_at") or i["updated"], reverse=True)

    total = sum(_int(i.get("sold_price")) or 0 for i in sold)
    # Share of the asking price: only items where both are known.
    pairs = [(_int(i.get("sold_price")), _int(i["data"].get("price"))) for i in sold]
    pairs = [(got, asked) for got, asked in pairs if got is not None and asked]
    share = round(100 * sum(g for g, _ in pairs) / sum(a for _, a in pairs)) if pairs else None

    days = []
    for i in sold:
        start, end = _time(i["created"]), _time(i.get("sold_at"))
        if start and end:
            days.append(max(0, (end.date() - start.date()).days))

    # The last months, the current one last.
    months = []
    year, month = today.year, today.month
    for _ in range(MONTHS):
        months.append({"year": year, "month": month, "total": 0, "count": 0})
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    months.reverse()
    for i in sold:
        t = _time(i.get("sold_at"))
        for m in months:
            if t and (t.year, t.month) == (m["year"], m["month"]):
                m["total"] += _int(i.get("sold_price")) or 0
                m["count"] += 1
    highest = max((m["total"] for m in months), default=0)
    for m in months:
        m["percent"] = round(100 * m["total"] / highest) if highest else 0

    channels: dict[str, dict[str, int]] = {}
    for i in sold:
        c = channels.setdefault(i.get("sold_via") or "", {"total": 0, "count": 0})
        c["total"] += _int(i.get("sold_price")) or 0
        c["count"] += 1

    def stock(states: tuple[str, ...]) -> dict[str, int]:
        part = [i for i in items if i["status"] in states]
        return {"count": len(part), "value": sum(_int(i["data"].get("price")) or 0 for i in part)}

    return {
        "total": total,
        "count": len(sold),
        "average": round(total / len(sold)) if sold else 0,
        "share": share,
        "days": round(sum(days) / len(days)) if days else None,
        "this_month": months[-1],
        "months": months,
        "channels": sorted(channels.items(), key=lambda kv: (-kv[1]["total"], kv[0])),
        "online": stock(("online",)),
        "drafts": stock(("draft",)),
        "sold": sold,
    }
