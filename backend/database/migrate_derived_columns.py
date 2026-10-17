"""
Adds two DERIVED columns to Medicines and fills them in. Safe to run more than once.

  python database/migrate_derived_columns.py

  release_type            VARCHAR(12) NULL  - sr / er / cr / pr / dt / odt / ... (see
                                              app/services/release_type.py); NULL = conventional
  composition_incomplete  BOOLEAN NOT NULL  - the product's name shows 3+ strengths but the
                                              stored composition lists <= 2 ingredients
                                              (see app/services/composition.py)

What it does and does not do:
  - ADDS columns only. Existing columns and rows are not altered or deleted;
    nothing but these two derived columns is written, and no row is removed.
  - Re-running only updates rows whose derived value differs from what is
    stored, so it is idempotent.
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app.db import get_connection
from app.services.composition import is_composition_incomplete
from app.services.release_type import derive_release_type

BATCH = 5000


def column_exists(cursor, column):
    cursor.execute(
        """SELECT COUNT(*) FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Medicines' AND COLUMN_NAME = %s""",
        (column,),
    )
    return cursor.fetchone()[0] > 0


def main():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for column, ddl in (
            ("release_type", "ALTER TABLE Medicines ADD COLUMN release_type VARCHAR(12) NULL AFTER pack_size"),
            ("composition_incomplete",
             "ALTER TABLE Medicines ADD COLUMN composition_incomplete BOOLEAN NOT NULL DEFAULT FALSE AFTER release_type"),
        ):
            if column_exists(cursor, column):
                print(f"{column} column already exists")
            else:
                cursor.execute(ddl)
                conn.commit()
                print(f"added Medicines.{column}")

        cursor.execute(
            "SELECT medicine_id, medicine_name, composition, pack_size, form, release_type, composition_incomplete FROM Medicines"
        )
        rows = cursor.fetchall()
        updates = []
        counts = collections.Counter()
        incomplete = 0
        for medicine_id, name, composition, pack_size, form, current_release, current_incomplete in rows:
            release = derive_release_type(name, pack_size, form)
            flag = int(is_composition_incomplete(name, composition))
            counts[release] += 1
            incomplete += flag
            if release != current_release or flag != int(current_incomplete or 0):
                updates.append((release, flag, medicine_id))

        for i in range(0, len(updates), BATCH):
            cursor.executemany(
                "UPDATE Medicines SET release_type = %s, composition_incomplete = %s WHERE medicine_id = %s",
                updates[i:i + BATCH],
            )
            conn.commit()

        print(f"rows scanned: {len(rows)}; derived columns written on {len(updates)} rows")
        print(f"composition_incomplete = 1 on {incomplete} rows")
        for value, n in counts.most_common():
            print(f"  release_type {str(value):10} {n}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
