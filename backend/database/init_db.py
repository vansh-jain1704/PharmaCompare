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


def split_statements(schema_sql):
    """
    The schema's statements, split on semicolons AFTER the comments are removed. A semicolon inside a comment (the
    Medicines.release_type note has one) used to cut a CREATE TABLE in half, so this script could not run end to end.
    """
    lines = []
    for line in schema_sql.splitlines():
        cut = line.find("--")
        if cut >= 0 and line[:cut].count("'") % 2 == 0:      # a "--" outside a quoted string starts a comment
            line = line[:cut]
        lines.append(line)
    return [statement.strip() for statement in chr(10).join(lines).split(";") if statement.strip()]


def run():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    statements = split_statements(schema_sql)

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
