"""
Imports DDInter 2.0's drug-drug interaction pairs into Drug_Interactions.
See database/PROVENANCE.md for what DDInter is and why it was chosen.

Run with:  python database/import_drug_interactions.py
Re-run safely with --force (truncates and reloads).

Source files: database/data/ddinter/code_{A,B,D,H,L,P,R,V}.csv
Download each from https://ddinter2.scbdd.com/download/ if missing.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app.db import get_connection

DDINTER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ddinter")
CODES = ["A", "B", "D", "H", "L", "P", "R", "V"]
DATA_SOURCE = "DDInter 2.0 (ddinter2.scbdd.com)"
BATCH_SIZE = 2000

INSERT_SQL = """
    INSERT INTO Drug_Interactions (drug_a, drug_b, drug_a_norm, drug_b_norm, severity, data_source)
    VALUES (%s, %s, %s, %s, %s, %s)
"""


def read_pairs():
    """Yields deduplicated (drug_a, drug_b, severity) triples across all 8
    files - the same unordered pair can appear in more than one category
    file, so we keep only the first severity we see for a given pair."""
    seen = {}
    for code in CODES:
        path = os.path.join(DDINTER_DIR, f"code_{code}.csv")
        if not os.path.exists(path):
            print(f"WARNING: missing {path}, skipping")
            continue
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                a, b = row["Drug_A"].strip(), row["Drug_B"].strip()
                if not a or not b:
                    continue
                key = tuple(sorted([a.lower(), b.lower()]))
                if key in seen:
                    continue
                seen[key] = True
                yield a, b, a.lower(), b.lower(), row["Level"].strip()


def run(force=False):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM Drug_Interactions")
    existing = cursor.fetchone()[0]
    if existing > 0:
        if not force:
            print(f"Drug_Interactions already has {existing} rows. Re-run with --force to wipe and re-import.")
            cursor.close()
            conn.close()
            sys.exit(1)
        print(f"--force given: clearing {existing} existing rows first.")
        cursor.execute("TRUNCATE TABLE Drug_Interactions")
        conn.commit()

    batch = []
    total = 0
    for a, b, a_norm, b_norm, severity in read_pairs():
        batch.append((a, b, a_norm, b_norm, severity, DATA_SOURCE))
        if len(batch) >= BATCH_SIZE:
            cursor.executemany(INSERT_SQL, batch)
            conn.commit()
            total += len(batch)
            print(f"  imported {total} pairs...")
            batch = []

    if batch:
        cursor.executemany(INSERT_SQL, batch)
        conn.commit()
        total += len(batch)

    cursor.execute("SELECT COUNT(*) FROM Drug_Interactions")
    final_count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    print(f"\nDone. Inserted {total} unique pairs. Drug_Interactions now has {final_count} rows.")


if __name__ == "__main__":
    run(force="--force" in sys.argv)
