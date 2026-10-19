"""
Checks every product in the Medicines table against itself (names, strengths, dosage forms, ingredients, prices) and prints what it finds, with
examples. READ-ONLY: it changes nothing. See app/services/data_validation_service.py for exactly what each check means and what it cannot say.

  python database/validate_medicines.py [--examples 5] [--json report.json]
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app import create_app
from app.db import get_connection
from app.services import data_validation_service


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--examples", type=int, default=3, help="examples to list per check")
    parser.add_argument("--json", help="also write the report to this file")
    args = parser.parse_args(argv)

    app = create_app()
    with app.app_context():
        conn = get_connection()
        cursor = conn.cursor()
        started = time.time()
        report = data_validation_service.scan_table(cursor, examples=args.examples)
        cursor.close()
        conn.close()

    print(f"checked {report['checked']:,} products in {time.time() - started:.0f}s; {report['with_notes']:,} have at least one note\n")
    for code, found in report["by_code"].items():
        level, text = data_validation_service.NOTES[code]
        print(f"{code:30} {found['count']:>8,}  [{level}] {text}")
        for example in found["examples"]:
            print(f"{'':30} {'':>8}    id {example['medicine_id']}: {example['name']}")
    print("\nA note is a reason to look twice, not a correction and not a verdict that a value is wrong or right.")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=1)
        print(f"written to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
