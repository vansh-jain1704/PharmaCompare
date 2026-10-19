"""
Pharmacy offers: what pharmacies have REPORTED (a price, a stock status, or both, and when they observed it).

Nothing here is ever invented or inferred: a medicine no pharmacy has reported on simply has no rows, and the app says
"not reported". Rows come only from a feed imported with database/import_pharmacy_feed.py.
"""
from app.db import get_connection


def get_observations(medicine_ids):
    """
    Every reported observation for these medicines, newest first, joined with the pharmacy and its data source.
    Returns {medicine_id: [row, ...]}.
    """
    ids = [int(i) for i in medicine_ids if i is not None]
    if not ids:
        return {}
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""SELECT o.offer_id, o.medicine_id, o.price, o.availability, o.quantity_available, o.observed_at,
                       ph.pharmacy_id, ph.name AS pharmacy_name, ph.city, ph.address,
                       ds.source_id, ds.source_key, ds.name AS source_name, ds.kind AS source_kind, ds.license AS source_license
                FROM Pharmacy_Offers o
                JOIN Pharmacies ph ON ph.pharmacy_id = o.pharmacy_id
                JOIN Data_Sources ds ON ds.source_id = ph.source_id
                WHERE o.medicine_id IN ({", ".join(["%s"] * len(ids))})
                ORDER BY o.observed_at DESC, o.offer_id DESC""",
            ids,
        )
        grouped = {}
        for row in cursor.fetchall():
            grouped.setdefault(row["medicine_id"], []).append(row)
        return grouped
    finally:
        cursor.close()
        conn.close()


def upsert_source(source_key, name, kind, url=None, license_text=None, notes=None):
    """Creates the data source if it does not exist and returns its source_id."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT source_id FROM Data_Sources WHERE source_key = %s", (source_key,))
        row = cursor.fetchone()
        if row:
            return row[0]
        cursor.execute(
            "INSERT INTO Data_Sources (source_key, name, kind, url, license, notes, retrieved_at) VALUES (%s, %s, %s, %s, %s, %s, NOW())",
            (source_key, name, kind, url, license_text, notes),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def get_or_create_pharmacy(source_id, name, city="", address=None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT pharmacy_id FROM Pharmacies WHERE name = %s AND city = %s AND source_id = %s", (name, city or "", source_id))
        row = cursor.fetchone()
        if row:
            return row[0]
        cursor.execute("INSERT INTO Pharmacies (name, city, address, source_id) VALUES (%s, %s, %s, %s)", (name, city or "", address, source_id))
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def insert_observation(pharmacy_id, medicine_id, price, availability, quantity_available, observed_at):
    """Records one observation. Returns True when it was new, False when the same observation was already recorded."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT IGNORE INTO Pharmacy_Offers (pharmacy_id, medicine_id, price, availability, quantity_available, observed_at)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (pharmacy_id, medicine_id, price, availability, quantity_available, observed_at),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def touch_source(source_key):
    """After a feed delivers: when it last delivered (retrieved_at) and how many observations it now holds (record_count)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE Data_Sources ds SET ds.retrieved_at = NOW(),
                      ds.record_count = (SELECT COUNT(*) FROM Pharmacy_Offers o JOIN Pharmacies ph ON ph.pharmacy_id = o.pharmacy_id WHERE ph.source_id = ds.source_id)
               WHERE ds.source_key = %s""",
            (source_key,),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def delete_source(source_key):
    """Removes a data source with its pharmacies and every observation (they cascade). Returns the number of sources removed."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM Data_Sources WHERE source_key = %s", (source_key,))
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()


def counts_for_source(source_key):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT COUNT(DISTINCT ph.pharmacy_id), COUNT(o.offer_id)
               FROM Data_Sources ds
               LEFT JOIN Pharmacies ph ON ph.source_id = ds.source_id
               LEFT JOIN Pharmacy_Offers o ON o.pharmacy_id = ph.pharmacy_id
               WHERE ds.source_key = %s""",
            (source_key,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()
