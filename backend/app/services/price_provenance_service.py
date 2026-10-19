"""
What a price on the screen or in the PDF actually is: where it came from, when, and whether it is live.

Two kinds exist, and they are never blurred:

  reference_dataset   the product's price in the imported community dataset. The date shown is the day that snapshot was IMPORTED here: the
                      source does not say when each price was true, so the date is never presented as "valid on". It is never live.
  pharmacy_reported   a price a pharmacy feed reported, with the pharmacy, the feed and the time it was observed (see offer_service). Shown
                      separately. Even a fresh report is "reported N hours ago", not "live": nothing here polls a pharmacy.

live_data_status() says, from the registry, whether any pharmacy feed has delivered anything. With none, the app says no live feed is
connected instead of leaving the reader to assume one is.
"""
from datetime import date, datetime

from app.config import Config

REFERENCE_BASIS = "reference_dataset"
SOURCE_KEY = "indian_medicine_dataset"
SOURCE_NAME = "Indian Medicine Dataset (community project on GitHub)"
WHAT_THE_DATE_MEANS = "the day this snapshot was imported here; the source does not say when each price was true"


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "")).date()
        except ValueError:
            return None
    return None


def _date_text(d):
    return f"{d.day} {d:%b %Y}"


def _age_text(days):
    if days <= 0:
        return "today"
    if days == 1:
        return "1 day ago"
    if days < 60:
        return f"{days} days ago"
    return f"{days // 30} months ago"


def reference_basis(price_date, today=None):
    """The provenance of a reference-dataset price, from the date its snapshot was imported. Never live."""
    imported = _as_date(price_date)
    base = {"basis": REFERENCE_BASIS, "live": False, "source_key": SOURCE_KEY, "source_name": SOURCE_NAME, "what_the_date_means": WHAT_THE_DATE_MEANS}
    if imported is None:
        return {**base, "imported_on": None, "age_days": None, "stale": None,
                "label": f"Reference price from the {SOURCE_NAME}. The import date is not recorded. Not a live price."}
    age = max(((today or date.today()) - imported).days, 0)
    stale = age > Config.REFERENCE_PRICE_STALE_DAYS
    label = f"Reference price from the {SOURCE_NAME}, imported {_date_text(imported)} ({_age_text(age)}). Not a live price."
    if stale:
        label += " This snapshot is old, so the price may have changed."
    return {**base, "imported_on": imported.isoformat(), "age_days": age, "stale": stale, "label": label}


def live_data_status(cursor):
    """
    Whether any pharmacy feed (not demo data) has delivered a price or a stock report, and when the latest report was observed.
    Counted now from the registry and the offers table: nothing is assumed.
    """
    cursor.execute(
        """SELECT COUNT(DISTINCT ds.source_id), COUNT(DISTINCT ph.pharmacy_id), COUNT(o.offer_id), MAX(o.observed_at), MAX(o.imported_at)
           FROM Data_Sources ds
           JOIN Pharmacies ph ON ph.source_id = ds.source_id
           JOIN Pharmacy_Offers o ON o.pharmacy_id = ph.pharmacy_id
           WHERE ds.kind = 'pharmacy_feed'"""
    )
    feeds, pharmacies, reports, latest_observed, latest_received = cursor.fetchone()
    connected = bool(reports)
    if not connected:
        statement = ("No live pharmacy price or stock feed is connected. Every price shown is a reference price from a dataset snapshot, and "
                     "no stock level is known.")
    else:
        statement = (f"{feeds} pharmacy feed{'s' if feeds != 1 else ''} ({pharmacies} pharmac{'ies' if pharmacies != 1 else 'y'}) have reported "
                     f"{reports:,} price or stock observation{'s' if reports != 1 else ''}; the latest was observed {latest_observed:%d %b %Y, %H:%M}. "
                     "These are shown separately from reference prices, with their age. They are reports, not a live connection to a pharmacy.")
    return {
        "live_feed_connected": connected, "feeds": feeds or 0, "pharmacies": pharmacies or 0, "reports": reports or 0,
        "latest_observed_at": latest_observed.isoformat() if latest_observed else None,
        "latest_received_at": latest_received.isoformat() if latest_received else None,
        "statement": statement,
    }


def dataset_basis(today=None):
    """
    The provenance of the reference dataset as a whole, for a heading or a footnote: the registry's date for the snapshot, otherwise the
    oldest import date on the Medicines table. Used where no single price is in front of the reader.
    """
    from app.db import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT retrieved_at FROM Data_Sources WHERE source_key = %s", (SOURCE_KEY,))
        row = cursor.fetchone()
        imported = row[0] if row and row[0] else None
        if imported is None:
            cursor.execute("SELECT MIN(imported_at) FROM Medicines")
            imported = cursor.fetchone()[0]
        return reference_basis(imported, today)
    finally:
        cursor.close()
        conn.close()
