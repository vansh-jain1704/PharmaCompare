import json

from app.db import get_connection


def create_user(name, email, phone, password_hash):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Users (name, email, phone, password) VALUES (%s, %s, %s, %s)",
            (name, email, phone, password_hash),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def get_user_by_email(email):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM Users WHERE email = %s", (email,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def get_user_by_id(user_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT user_id, name, email, phone, allergies, created_at FROM Users WHERE user_id = %s",
            (user_id,),
        )
        return _decode_allergies(cursor.fetchone())
    finally:
        cursor.close()
        conn.close()


def _decode_allergies(row):
    """MySQL returns JSON columns as text; callers get a real list."""
    if row is not None:
        raw = row.get("allergies")
        row["allergies"] = json.loads(raw) if raw else []
    return row


def get_user_allergies(user_id):
    user = get_user_by_id(user_id)
    return (user or {}).get("allergies") or []


def set_user_allergies(user_id, allergies):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE Users SET allergies = %s WHERE user_id = %s",
            (json.dumps(allergies), user_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
