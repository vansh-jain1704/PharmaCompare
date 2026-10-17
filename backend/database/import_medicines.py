"""
One-time bulk import of the community Indian medicine dataset into the
Medicines table. See database/PROVENANCE.md for what this data is and
where it came from.

Run with:  python database/import_medicines.py
Re-run safely: if Medicines already has rows, it will refuse to run unless
you pass --force (which truncates Medicines first - safe, since nothing
else references it yet in a way that survives a re-import; see the
--force branch below for exactly what it does).
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app.db import get_connection
from app.services.composition import is_composition_incomplete
from app.services.release_type import derive_release_type

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "indian_medicine_data.csv")
DATA_SOURCE_TAG = "community_dataset:indian-medicine-dataset-github"
BATCH_SIZE = 2000

COMPOSITION_RE = re.compile(r"^\s*(.*?)\s*\(([^)]*)\)\s*$")

FORM_KEYWORDS = [
    "Eye Drop", "Ear Drop", "Nasal Spray", "Tablet", "Capsule", "Syrup",
    "Injection", "Infusion", "Cream", "Ointment", "Gel", "Drops", "Drop",
    "Lotion", "Suspension", "Powder", "Spray", "Inhaler", "Solution",
    "Sachet", "Soap", "Shampoo", "Lozenges", "Lozenge", "Patch",
    "Suppository", "Granules", "Emulsion", "Paste", "Mouthwash",
    "Respules", "Rotacap", "Liquid", "Cartridge", "Penfill",
]
FORM_PATTERNS = [(kw, re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)) for kw in FORM_KEYWORDS]


def parse_salt_strength(composition_text):
    """'Amoxycillin  (500mg) ' -> ('Amoxycillin', '500mg'). Never guesses -
    returns (text, None) if there's no '(...)' to parse."""
    text = composition_text.strip()
    if not text:
        return None, None
    m = COMPOSITION_RE.match(text)
    if m and m.group(1).strip():
        return m.group(1).strip(), m.group(2).strip()
    return text, None


def extract_form(name):
    for label, pattern in FORM_PATTERNS:
        if pattern.search(name):
            return label
    return None


def build_composition_display(comp1, comp2):
    parts = [p.strip() for p in (comp1, comp2) if p and p.strip()]
    return " + ".join(parts) if parts else None


def read_rows():
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            comp1 = row["short_composition1"]
            comp2 = row["short_composition2"]
            primary_salt, strength = parse_salt_strength(comp1)
            secondary_salt, _ = parse_salt_strength(comp2) if comp2.strip() else (None, None)

            price_raw = row["price(₹)"].strip()
            try:
                price = float(price_raw) if price_raw else None
            except ValueError:
                price = None

            name = row["name"].strip()
            form = extract_form(row["name"])
            pack_size = row["pack_size_label"].strip() or None

            yield (
                name,                                                  # medicine_name
                build_composition_display(comp1, comp2),               # composition
                form,                                                  # form
                strength,                                              # strength
                primary_salt,                                          # primary_salt
                secondary_salt,                                        # secondary_salt
                row["manufacturer_name"].strip(),                      # manufacturer
                pack_size,                                             # pack_size
                price,                                                 # price
                row["Is_discontinued"].strip().upper() == "TRUE",      # is_discontinued
                row["id"].strip(),                                     # source_dataset_id
                DATA_SOURCE_TAG,                                       # data_source
                derive_release_type(name, pack_size, form),            # release_type
                int(is_composition_incomplete(name, build_composition_display(comp1, comp2))),  # composition_incomplete
            )


INSERT_SQL = """
    INSERT INTO Medicines
        (medicine_name, composition, form, strength, primary_salt, secondary_salt,
         manufacturer, pack_size, price, is_discontinued, source_dataset_id, data_source,
         release_type, composition_incomplete)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def run(force=False):
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: dataset CSV not found at {CSV_PATH}")
        print("Download it from https://github.com/junioralive/Indian-Medicine-Dataset "
              "(DATA/indian_medicine_data.csv) and place it there first.")
        sys.exit(1)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM Medicines")
    existing = cursor.fetchone()[0]
    if existing > 0:
        if not force:
            print(f"Medicines already has {existing} rows. Re-run with --force to wipe and re-import.")
            cursor.close()
            conn.close()
            sys.exit(1)
        print(f"--force given: clearing {existing} existing Medicines rows first.")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute("TRUNCATE TABLE Medicines")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()

    batch = []
    total = 0
    for row in read_rows():
        batch.append(row)
        if len(batch) >= BATCH_SIZE:
            cursor.executemany(INSERT_SQL, batch)
            conn.commit()
            total += len(batch)
            print(f"  imported {total} rows...")
            batch = []

    if batch:
        cursor.executemany(INSERT_SQL, batch)
        conn.commit()
        total += len(batch)

    cursor.execute("SELECT COUNT(*) FROM Medicines")
    final_count = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    print(f"\nDone. Inserted {total} rows. Medicines table now has {final_count} rows.")


if __name__ == "__main__":
    run(force="--force" in sys.argv)
