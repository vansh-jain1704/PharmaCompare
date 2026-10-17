"""
One-time setup script: creates all PharmaCompare tables from schema.sql.
Run with:  python database/init_db.py
Safe to re-run - every statement uses CREATE TABLE IF NOT EXISTS.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import get_connection

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def run():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    statements = [s.strip() for s in schema_sql.split(";") if s.strip()]

    conn = get_connection()
    cursor = conn.cursor()

    for statement in statements:
        cursor.execute(statement)
        print(f"Executed: {statement.splitlines()[0][:60]}...")

    conn.commit()
    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    print(f"\nDone. {len(tables)} tables in the database:")
    for t in tables:
        print(f"  - {t}")


if __name__ == "__main__":
    run()
