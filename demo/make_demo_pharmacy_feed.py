r"""
Writes a SYNTHETIC pharmacy feed CSV so the demo can show how pharmacy-reported price and stock appear on screen.

Every figure here is invented for the demo: prices are the dataset price nudged by a fixed percentage, stock statuses are assigned by hand,
and the timestamps are relative to now so some reports are fresh and one is stale. Import it ONLY as demo data:

  python demo/make_demo_pharmacy_feed.py demo/demo_pharmacy_feed.csv
  backend\venv\Scripts\python.exe backend/database/import_pharmacy_feed.py demo/demo_pharmacy_feed.csv --source-key demo_feed --name "Demo pharmacy feed" --kind synthetic_demo
  backend\venv\Scripts\python.exe backend/database/import_pharmacy_feed.py --remove-source demo_feed        # when finished

It is stored as kind synthetic_demo and labelled "Demo data" wherever the app shows it. Never import invented figures as a real feed.
"""
import csv
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

PRODUCTS = ["Dolo 650 Tablet", "Pan-D Capsule PR"]
# pharmacy, city, price change, stock, quantity, hours ago
REPORTS = [
    ("Demo Pharmacy A", "Demo City", -0.05, "in_stock", 24, 2),
    ("Demo Pharmacy B", "Demo City", 0.04, "limited", 3, 6),
    ("Demo Pharmacy C", "Demo Town", 0.00, "out_of_stock", "", 30),
    ("Demo Pharmacy D", "Demo Town", 0.02, "in_stock", 10, 24 * 20),      # old enough to be shown as out of date
]


def main(path):
    from app import create_app
    from app.db import get_connection
    app = create_app()
    now = datetime.now()
    with app.app_context():
        conn = get_connection()
        cur = conn.cursor()
        rows = []
        for name in PRODUCTS:
            cur.execute("SELECT medicine_id, price FROM Medicines WHERE medicine_name = %s ORDER BY medicine_id LIMIT 1", (name,))
            found = cur.fetchone()
            if not found:
                print(f"skipped {name}: not in the catalogue")
                continue
            medicine_id, price = found
            for pharmacy, city, change, stock, qty, hours in REPORTS:
                rows.append([pharmacy, city, medicine_id, f"{float(price) * (1 + change):.2f}", stock, qty, (now - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")])
        cur.close()
        conn.close()
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pharmacy", "city", "medicine_id", "price", "availability", "quantity", "observed_at"])
        writer.writerows(rows)
    print(f"wrote {len(rows)} synthetic reports to {path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python demo/make_demo_pharmacy_feed.py OUTPUT.csv")
    main(sys.argv[1])
