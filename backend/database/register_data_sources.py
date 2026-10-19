"""
Records, in the Data_Sources registry, which data PharmaCompare uses and how good it measures: the medicine dataset and the interaction
dataset, with their record counts, import dates, licences as recorded (NULL when the repository does not record one) and a quality check
counted from the live tables.

  python database/register_data_sources.py

Safe to re-run (it refreshes these two rows from the tables as they are now). It never touches pharmacy feeds and never changes a
medicine or an interaction.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app.db import get_connection
from app.services import data_sources_service


def main():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        rows = data_sources_service.build_registry_rows(cursor, date.today().isoformat())
    finally:
        cursor.close()
        conn.close()
    data_sources_service.register(rows)
    for r in rows:
        print(f"{r['source_key']}: {r['record_count']:,} records | licence: {r['license'] or 'not recorded'}")
        print(f"   {r['notes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
