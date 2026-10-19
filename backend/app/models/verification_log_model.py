"""
The review trail for manual medicine verification, kept in the existing System_Logs table (no schema change).

Every time a person settles a line - confirms a product, says "none of these", or adds a medicine by hand -
one row is written that records WHAT they decided and WHAT they were looking at: the OCR text of the line,
the status and confidence the matcher had given it, the candidates it was shown, and any warnings they were
shown and acknowledged. The line itself keeps its original OCR text, so the decision can be reviewed later.

`details` is JSON text that always begins with the prescription id (`{"prescription_id": 12, ...`), which is
how one prescription's rows are found and deleted with it: nothing from a deleted prescription is kept.
"""
import json

from app.db import get_connection

ACTION = "medicine_verification"

DECISION_CONFIRMED = "confirmed"
DECISION_UNMATCHED = "unmatched"
DECISION_ADDED_MANUALLY = "added_manually"
DECISION_ENTERED_BY_USER = "entered_by_user"


def _prefix(prescription_id):
    return f'{{"prescription_id": {int(prescription_id)},%'


def log_decision(user_id, prescription_id, pm_id, decision, **details):
    """Writes one decision row; returns its log_id. `details` is stored as given (JSON-serialisable)."""
    payload = {"prescription_id": int(prescription_id), "pm_id": pm_id, "decision": decision, **details}
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO System_Logs (user_id, action, details) VALUES (%s, %s, %s)",
            (user_id, ACTION, json.dumps(payload, default=str)),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def get_decisions(prescription_id):
    """Every decision recorded for one prescription, oldest first, each with its timestamp."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT log_id, timestamp, details FROM System_Logs WHERE action = %s AND details LIKE %s ORDER BY log_id",
            (ACTION, _prefix(prescription_id)),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    decisions = []
    for row in rows:
        try:
            details = json.loads(row["details"])
        except (TypeError, ValueError):
            continue
        if details.get("prescription_id") != int(prescription_id):
            continue
        decisions.append({"log_id": row["log_id"], "decided_at": row["timestamp"].isoformat(), **details})
    return decisions


def latest_decision_by_pm(prescription_id):
    """{pm_id: the most recent decision for that line}."""
    latest = {}
    for decision in get_decisions(prescription_id):
        if decision.get("pm_id") is not None:
            latest[decision["pm_id"]] = decision
    return latest


def delete_decisions(prescription_id, cursor=None):
    """Removes every decision row of one prescription (used when the prescription itself is deleted)."""
    own = cursor is None
    conn = None
    if own:
        conn = get_connection()
        cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM System_Logs WHERE action = %s AND details LIKE %s", (ACTION, _prefix(prescription_id)))
        if own:
            conn.commit()
    finally:
        if own:
            cursor.close()
            conn.close()
