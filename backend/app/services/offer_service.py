"""
What pharmacies have reported about a medicine (price and stock), worded honestly.

Every figure carries WHO reported it, WHICH feed it came from and HOW OLD it is, and nothing is guessed:

  - a medicine with no reports says "not reported" (never "in stock" and never "out of stock");
  - a stock report older than OFFER_STOCK_MAX_AGE_HOURS is shown as "last reported ... ago (may have changed)", and is NOT
    counted as in stock; a price report older than OFFER_PRICE_MAX_AGE_DAYS is shown with its age and labelled stale;
  - demo data (kind "synthetic_demo") is always labelled as such and is never presented as real;
  - the dataset's own price (Medicines.price) is NOT a pharmacy offer and is never mixed in here.

The two age limits are policy settings (app/config.py, overridable from the environment), not measurements: stock changes
faster than prices, so stock goes stale sooner. The real age is always displayed whatever the limit is.
"""
from datetime import datetime

from app.config import Config
from app.models.offer_model import get_observations

AVAILABILITY_VALUES = ("in_stock", "limited", "out_of_stock", "unknown")
AVAILABILITY_LABELS = {"in_stock": "In stock", "limited": "Limited stock", "out_of_stock": "Out of stock", "unknown": "Stock not stated"}
SOURCE_KIND_NOTES = {"synthetic_demo": "Demo data: not a real pharmacy and not a real price"}
MAX_ITEMS = 8


def _age_text(age_hours):
    if age_hours < 1:
        return "less than an hour ago"
    if age_hours < 48:
        hours = int(age_hours)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = int(age_hours // 24)
    return f"{days} days ago"


def latest_per_pharmacy(rows):
    """The newest observation of each pharmacy (rows arrive newest first)."""
    seen, latest = set(), []
    for row in rows:
        if row["pharmacy_id"] not in seen:
            seen.add(row["pharmacy_id"])
            latest.append(row)
    return latest


def describe(rows, now=None):
    """
    The offers for ONE medicine as the API and the screens present them:
      {"items": [...], "count": n, "availability": {...}, "cheapest": {...} or None, "has_demo_data": bool}
    """
    now = now or datetime.now()
    items = []
    for row in latest_per_pharmacy(rows):
        age_hours = max((now - row["observed_at"]).total_seconds() / 3600.0, 0.0)
        has_price = row["price"] is not None
        stock_fresh = age_hours <= Config.OFFER_STOCK_MAX_AGE_HOURS
        price_fresh = age_hours <= Config.OFFER_PRICE_MAX_AGE_DAYS * 24
        items.append({
            "pharmacy": row["pharmacy_name"], "city": row["city"] or None,
            "price": float(row["price"]) if has_price else None,
            "price_stale": bool(has_price and not price_fresh),
            "availability": row["availability"], "availability_label": AVAILABILITY_LABELS.get(row["availability"], "Stock not stated"),
            "stock_stale": not stock_fresh,
            "quantity_available": row["quantity_available"],
            "observed_at": row["observed_at"].isoformat(), "age": _age_text(age_hours), "age_hours": round(age_hours, 1),
            "source": row["source_name"], "source_kind": row["source_kind"], "demo": row["source_kind"] == "synthetic_demo",
            "note": SOURCE_KIND_NOTES.get(row["source_kind"]),
        })
    items.sort(key=lambda i: (i["price"] is None, i["price"] if i["price"] is not None else 0, i["pharmacy"]))

    priced_fresh = [i for i in items if i["price"] is not None and not i["price_stale"]]
    return {
        "items": items[:MAX_ITEMS],
        "count": len(items),
        "availability": availability_summary(items),
        "cheapest": min(priced_fresh, key=lambda i: i["price"]) if priced_fresh else None,
        "has_demo_data": any(i["demo"] for i in items),
    }


def availability_summary(items):
    """
    One honest statement of availability from the latest report of each pharmacy.
    status: "not_reported" | "in_stock" | "limited" | "out_of_stock" | "mixed" | "stale"
    Only FRESH stock reports count as a statement about now.
    """
    reporting = [i for i in items if i["availability"] in ("in_stock", "limited", "out_of_stock")]
    if not reporting:
        return {"status": "not_reported", "label": "No pharmacy has reported stock for this medicine", "pharmacies_reporting": 0}
    fresh = [i for i in reporting if not i["stock_stale"]]
    newest = min(reporting, key=lambda i: i["age_hours"])
    if not fresh:
        return {"status": "stale", "pharmacies_reporting": len(reporting),
                "label": f"Last reported {newest['age']} ({newest['availability_label'].lower()} at {newest['pharmacy']}): may have changed"}
    in_stock = [i for i in fresh if i["availability"] == "in_stock"]
    limited = [i for i in fresh if i["availability"] == "limited"]
    out = [i for i in fresh if i["availability"] == "out_of_stock"]
    where = f"{len(fresh)} pharmacy report{'s' if len(fresh) != 1 else ''}"
    if in_stock and not out and not limited:
        status, label = "in_stock", f"In stock at {len(in_stock)} of {where}"
    elif limited and not out:
        status, label = "limited", f"Limited stock at {len(limited)} of {where}"
    elif out and not in_stock and not limited:
        status, label = "out_of_stock", f"Out of stock at all {len(out)} reporting pharmacies"
    else:
        status, label = "mixed", f"In stock at {len(in_stock) + len(limited)}, out of stock at {len(out)} ({where})"
    latest_hours = min(i["age_hours"] for i in fresh)
    return {"status": status, "label": f"{label}, latest report {_age_text(latest_hours)}", "pharmacies_reporting": len(fresh)}


def offers_for_medicines(medicine_ids, now=None):
    """{medicine_id: describe(rows)} for every medicine that has at least one report (others are absent)."""
    grouped = get_observations(medicine_ids)
    return {mid: describe(rows, now) for mid, rows in grouped.items()}
