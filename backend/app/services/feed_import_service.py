"""
Importing a pharmacy price / stock feed, strictly.

A feed is a CSV a pharmacy (or a partner) supplies. Because it becomes what the app tells a patient about price and stock, the importer
accepts a row ONLY when it can be sure of every part of it, and rejects the rest with the reason (it never guesses):

  - observed_at is required (a report with no time is not accepted) and may not be in the future;
  - the product must resolve to EXACTLY ONE catalogue entry: by medicine_id, or by exact name (plus manufacturer / pack size when
    given). No match, or several, rejects the row, naming how many;
  - a price must be a positive number; a stock word the importer does not recognise is rejected (not read as "unknown");
  - a row that reports neither a price nor a stock status reports nothing, and is rejected.

Columns (any order, case-insensitive; aliases in parentheses):
  pharmacy (pharmacy_name), city, medicine_name (product), manufacturer, pack_size, medicine_id,
  price, availability (stock, stock_status), quantity (quantity_available), observed_at (reported_at, timestamp)
"""
import csv
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from app.db import get_connection
from app.models import offer_model
from app.services.offer_service import AVAILABILITY_VALUES

ALIASES = {
    "pharmacy_name": "pharmacy", "product": "medicine_name", "name": "medicine_name", "stock": "availability",
    "stock_status": "availability", "quantity_available": "quantity", "reported_at": "observed_at", "timestamp": "observed_at",
}
STOCK_WORDS = {
    "in_stock": "in_stock", "in stock": "in_stock", "available": "in_stock", "yes": "in_stock",
    "limited": "limited", "low": "limited", "limited stock": "limited", "low stock": "limited",
    "out_of_stock": "out_of_stock", "out of stock": "out_of_stock", "unavailable": "out_of_stock", "no": "out_of_stock",
    "unknown": "unknown", "": "unknown",
}
KINDS = ("pharmacy_feed", "synthetic_demo")
CLOCK_SKEW = timedelta(minutes=5)


class RowRejected(Exception):
    """Why one row was not accepted."""


def _normalise_header(name):
    key = (name or "").strip().lower().replace(" ", "_")
    return ALIASES.get(key, key)


def read_csv(path):
    """[(line number, {normalised column: text})] for the data rows of a CSV file."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for index, raw in enumerate(reader, start=2):
            rows.append((index, {_normalise_header(k): (v or "").strip() for k, v in raw.items() if k is not None}))
        return rows


def parse_observed_at(text, now=None):
    if not text:
        raise RowRejected("observed_at is missing: a report with no time is not accepted")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            value = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    else:
        raise RowRejected(f"observed_at {text!r} is not a date and time (use YYYY-MM-DD HH:MM)")
    if value > (now or datetime.now()) + CLOCK_SKEW:
        raise RowRejected(f"observed_at {text!r} is in the future")
    return value


def parse_price(text):
    if text == "":
        return None
    try:
        value = Decimal(text.replace(",", ""))
    except InvalidOperation:
        raise RowRejected(f"price {text!r} is not a number")
    if value <= 0 or value >= Decimal("10000000"):
        raise RowRejected(f"price {text!r} is not a plausible positive price")
    return value.quantize(Decimal("0.01"))


def parse_availability(text):
    key = (text or "").strip().lower()
    if key not in STOCK_WORDS:
        raise RowRejected(f"stock status {text!r} is not recognised (use in_stock, limited, out_of_stock or leave it blank)")
    return STOCK_WORDS[key]


def parse_quantity(text):
    if text == "":
        return None
    if not text.isdigit():
        raise RowRejected(f"quantity {text!r} is not a whole number")
    return int(text)


def resolve_medicine(row, cursor):
    """The one catalogue medicine_id this row names, or RowRejected. Never picks among several."""
    if row.get("medicine_id"):
        if not row["medicine_id"].isdigit():
            raise RowRejected(f"medicine_id {row['medicine_id']!r} is not a whole number")
        cursor.execute("SELECT medicine_id FROM Medicines WHERE medicine_id = %s", (int(row["medicine_id"]),))
        if not cursor.fetchone():
            raise RowRejected(f"medicine_id {row['medicine_id']} is not in the catalogue")
        return int(row["medicine_id"])
    name = row.get("medicine_name", "")
    if not name:
        raise RowRejected("the row names no medicine (give medicine_name or medicine_id)")
    clauses, params = ["LOWER(medicine_name) = %s"], [name.lower()]
    for column in ("manufacturer", "pack_size"):
        if row.get(column):
            clauses.append(f"LOWER({column}) = %s")
            params.append(row[column].lower())
    cursor.execute(f"SELECT medicine_id FROM Medicines WHERE {' AND '.join(clauses)} LIMIT 5", params)
    found = [r[0] for r in cursor.fetchall()]
    if not found:
        raise RowRejected(f"no catalogue product is named exactly {name!r}")
    if len(found) > 1:
        raise RowRejected(f"{name!r} is ambiguous ({len(found)}+ products: ids {found[:3]}): add manufacturer, pack_size or medicine_id")
    return found[0]


def validate_row(row, cursor, now=None):
    """The clean values of one row, or RowRejected."""
    if not row.get("pharmacy"):
        raise RowRejected("the row names no pharmacy")
    observed_at = parse_observed_at(row.get("observed_at", ""), now)
    price = parse_price(row.get("price", ""))
    availability = parse_availability(row.get("availability", ""))
    quantity = parse_quantity(row.get("quantity", ""))
    if price is None and availability == "unknown":
        raise RowRejected("the row reports neither a price nor a stock status")
    medicine_id = resolve_medicine(row, cursor)
    return {"pharmacy": row["pharmacy"], "city": row.get("city", ""), "medicine_id": medicine_id, "price": price,
            "availability": availability, "quantity": quantity, "observed_at": observed_at}


def import_feed(rows, source_key, source_name, kind="pharmacy_feed", url=None, license_text=None, notes=None, dry_run=False, now=None):
    """
    Imports parsed rows. Returns a report:
      {"read", "imported", "duplicates", "rejected": [(line, reason, row)], "pharmacies", "dry_run"}
    A dry run validates and resolves everything and writes nothing (not even the source).
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    report = {"read": len(rows), "imported": 0, "duplicates": 0, "rejected": [], "pharmacies": 0, "dry_run": dry_run}
    conn = get_connection()
    cursor = conn.cursor()
    try:
        clean = []
        for line, row in rows:
            try:
                clean.append(validate_row(row, cursor, now))
            except RowRejected as exc:
                report["rejected"].append((line, str(exc), row))
    finally:
        cursor.close()
        conn.close()
    if dry_run:
        report["imported"] = len(clean)
        report["pharmacies"] = len({(c["pharmacy"], c["city"]) for c in clean})
        return report
    if not clean:
        return report

    source_id = offer_model.upsert_source(source_key, source_name, kind, url, license_text, notes)
    pharmacy_ids = {}
    for item in clean:
        key = (item["pharmacy"], item["city"])
        if key not in pharmacy_ids:
            pharmacy_ids[key] = offer_model.get_or_create_pharmacy(source_id, item["pharmacy"], item["city"])
        if offer_model.insert_observation(pharmacy_ids[key], item["medicine_id"], item["price"], item["availability"], item["quantity"], item["observed_at"]):
            report["imported"] += 1
        else:
            report["duplicates"] += 1
    report["pharmacies"] = len(pharmacy_ids)
    offer_model.touch_source(source_key)
    return report
