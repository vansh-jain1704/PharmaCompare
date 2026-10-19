"""
Receiving pharmacy price and stock reports pushed by a partner's own system.

This is the only way live inventory can reach PharmaCompare without someone running an import by hand. It is deliberately a RECEIVER: no pharmacy
inventory API is connected, none is polled, and nothing here is invented. A report is accepted only if it passes exactly the same strict rules as
a CSV feed (feed_import_service): an observation time, one unambiguous catalogue product, a recognisable price and/or stock status. Rejected rows
come back with their reasons. Reports are shown with the pharmacy, the feed and their age, never as a live connection.

Limits: a request has a bounded size and row count, and a key has a bounded request rate, so one partner cannot flood the table or the server.
"""
import threading
import time
from collections import defaultdict, deque

from app.config import Config
from app.services import feed_import_service

ACCEPTED_COLUMNS = {"pharmacy", "city", "medicine_id", "medicine_name", "manufacturer", "pack_size", "price", "availability", "quantity", "observed_at"}
MAX_FIELD_CHARS = 200

_calls = defaultdict(deque)
_lock = threading.Lock()


class FeedRejected(Exception):
    """The request as a whole cannot be used. The message is safe to return."""


def too_many_requests(key_id, now=None):
    """True when this key has used up its requests for the last minute (and records this one otherwise)."""
    now = time.monotonic() if now is None else now
    with _lock:
        window = _calls[key_id]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= Config.PARTNER_FEED_REQUESTS_PER_MINUTE:
            return True
        window.append(now)
        return False


def reset_rate_limits():
    with _lock:
        _calls.clear()


def rows_from_body(body):
    """[(line, {column: text})] from the JSON body, or FeedRejected. Values are kept as text for the importer to validate."""
    if not isinstance(body, dict) or not isinstance(body.get("rows"), list):
        raise FeedRejected('send a JSON object like {"rows": [ ... ]}')
    rows = body["rows"]
    if not rows:
        raise FeedRejected("rows is empty")
    if len(rows) > Config.PARTNER_FEED_MAX_ROWS:
        raise FeedRejected(f"at most {Config.PARTNER_FEED_MAX_ROWS} rows per request")
    out = []
    for number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            out.append((number, {"__invalid__": "row is not an object"}))
            continue
        clean = {}
        for key, value in row.items():
            column = feed_import_service._normalise_header(str(key))
            if column not in ACCEPTED_COLUMNS:
                continue
            if value is None:
                text = ""
            elif isinstance(value, bool) or isinstance(value, (list, dict)):
                out.append((number, {"__invalid__": f"{column} must be text or a number"}))
                clean = None
                break
            else:
                text = str(value).strip()
            if len(text) > MAX_FIELD_CHARS:
                out.append((number, {"__invalid__": f"{column} is longer than {MAX_FIELD_CHARS} characters"}))
                clean = None
                break
            clean[column] = text
        if clean is not None:
            out.append((number, clean))
    return out


def ingest(source, body, dry_run=False):
    """
    Imports the rows for the feed source the key belongs to. Returns the importer's report as plain JSON:
      {"read", "imported", "duplicates", "rejected": [{"row", "reason"}], "pharmacies", "dry_run"}
    """
    rows = rows_from_body(body)
    invalid = [(n, r["__invalid__"]) for n, r in rows if "__invalid__" in r]
    valid = [(n, r) for n, r in rows if "__invalid__" not in r]
    report = feed_import_service.import_feed(valid, source["source_key"], source["source_name"], kind="pharmacy_feed", dry_run=dry_run) if valid else {
        "read": 0, "imported": 0, "duplicates": 0, "rejected": [], "pharmacies": 0, "dry_run": dry_run}
    rejected = [{"row": n, "reason": reason} for n, reason in invalid] + [{"row": line, "reason": reason} for line, reason, _ in report["rejected"]]
    rejected.sort(key=lambda r: r["row"])
    return {"read": len(rows), "imported": report["imported"], "duplicates": report["duplicates"], "rejected": rejected,
            "pharmacies": report["pharmacies"], "dry_run": dry_run}
