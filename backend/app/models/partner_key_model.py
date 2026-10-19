"""
API keys for pharmacy partners who push price and stock reports (see app/routes/feeds.py).

Each key belongs to one pharmacy-feed data source. Only a SHA-256 hash of the key is stored, so a database leak does not leak working keys,
and the key itself is shown exactly once, when it is created (database/manage_partner_keys.py). A revoked key stops working at once.
"""
import hashlib
import secrets

from app.db import get_connection

KEY_PREFIX = "pck_"


def hash_key(token):
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def create_key(source_id, label):
    """Creates a key for a feed source. Returns (key_id, the key). The key is not recoverable afterwards."""
    token = KEY_PREFIX + secrets.token_urlsafe(32)
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Partner_Keys (source_id, label, key_prefix, key_hash) VALUES (%s, %s, %s, %s)",
            (source_id, label, token[:8], hash_key(token)),
        )
        conn.commit()
        return cursor.lastrowid, token
    finally:
        cursor.close()
        conn.close()


def find_active(token):
    """The feed source this key may report for, or None (unknown or revoked). {key_id, source_id, source_key, source_name, kind}."""
    if not token or not token.startswith(KEY_PREFIX) or len(token) > 200:
        return None
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT pk.key_id, pk.source_id, ds.source_key, ds.name AS source_name, ds.kind
               FROM Partner_Keys pk JOIN Data_Sources ds ON ds.source_id = pk.source_id
               WHERE pk.key_hash = %s AND pk.revoked_at IS NULL""",
            (hash_key(token),),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def touch(key_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE Partner_Keys SET last_used_at = NOW() WHERE key_id = %s", (key_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def revoke(key_id):
    """Returns True when a live key was revoked."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE Partner_Keys SET revoked_at = NOW() WHERE key_id = %s AND revoked_at IS NULL", (key_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def list_keys():
    """Every key with what it belongs to. Never the key or its hash."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT pk.key_id, pk.label, pk.key_prefix, pk.created_at, pk.last_used_at, pk.revoked_at, ds.source_key, ds.name AS source_name
               FROM Partner_Keys pk JOIN Data_Sources ds ON ds.source_id = pk.source_id ORDER BY pk.key_id"""
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
