"""
Read-only data-quality audit of the Medicines table.

  python database/audit_dataset.py            # report to the console
  python database/audit_dataset.py --csv DIR  # also write sample rows as CSV files into DIR

This script ONLY runs SELECT statements. It never inserts, updates or deletes,
and it changes nothing about the data: it exists to show what is wrong so a
person can decide what to do. Nothing here is a verdict that a row is "bad" -
every list is a set of rows worth looking at.
"""
import argparse
import collections
import csv
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app.db import get_connection
from app.services.composition import composition_key, ingredient_numerators, split_ingredients
from app.services import price_quality

STRENGTH_OK_RE = re.compile(r"^\d+(?:\.\d+)?\s*(?:mg|mcg|ug|gm|g|ml|iu|units?|%)(?:\s*(?:w/[vw]|/\s*\d*(?:\.\d+)?\s*(?:ml|mg|g|gm)?))?\s*\S*$", re.IGNORECASE)
THREE_STRENGTHS_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:mg|mcg)?\s*/\s*\d+(?:\.\d+)?\s*(?:mg|mcg)?\s*/\s*\d+(?:\.\d+)?\s*(?:mg|mcg)", re.IGNORECASE)


class Report:
    def __init__(self, csv_dir):
        self.csv_dir = csv_dir
        if csv_dir:
            os.makedirs(csv_dir, exist_ok=True)

    def section(self, title):
        print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)

    def line(self, text):
        print("  " + text)

    def sample(self, name, rows, columns, show=5):
        for r in rows[:show]:
            self.line("e.g. " + " | ".join(str(r.get(c))[:44] for c in columns))
        if self.csv_dir and rows:
            path = os.path.join(self.csv_dir, f"{name}.csv")
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            self.line(f"(all {len(rows)} rows written to {path})")


def run(csv_dir=None):
    rep = Report(csv_dir)
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT COUNT(*) n FROM Medicines")
        total = cur.fetchone()["n"]
        rep.section(f"MEDICINES TABLE: {total} rows")

        # ---- 1. duplicates -----------------------------------------------------------------
        rep.section("1. Duplicate records")
        cur.execute("""SELECT medicine_name, manufacturer, strength, form, pack_size, composition,
                              COUNT(*) copies, COUNT(DISTINCT price) distinct_prices, MIN(price) lo, MAX(price) hi, MIN(medicine_id) first_id
                       FROM Medicines GROUP BY medicine_name, manufacturer, strength, form, pack_size, composition
                       HAVING copies > 1 ORDER BY copies DESC""")
        dup = cur.fetchall()
        extra = sum(r["copies"] - 1 for r in dup)
        rep.line(f"exact duplicates (same name, maker, strength, form, pack, composition): {len(dup)} groups, {extra} surplus rows")
        rep.line(f"  of these, {sum(1 for r in dup if r['distinct_prices'] > 1)} groups carry DIFFERENT prices (so which one is right is unknown)")
        rep.sample("duplicates", dup, ["medicine_name", "manufacturer", "strength", "pack_size", "copies", "lo", "hi", "first_id"])

        cur.execute("""SELECT LOWER(REPLACE(medicine_name,' ','')) k, LOWER(REPLACE(IFNULL(manufacturer,''),' ','')) m, COUNT(*) n
                       FROM Medicines GROUP BY k, m HAVING n > 1""")
        near = cur.fetchall()
        rep.line(f"duplicates after ignoring spacing/case in name+maker: {len(near)} groups (includes the exact ones; a different strength/pack may legitimately share a name)")

        # ---- 2. names ----------------------------------------------------------------------
        rep.section("2. Inconsistent names")
        cur.execute("""SELECT SUM(medicine_name LIKE '%  %') double_space, SUM(medicine_name <> TRIM(medicine_name)) padded,
                              SUM(composition LIKE '%  %') comp_double_space FROM Medicines""")
        r = cur.fetchone()
        rep.line(f"names with double spaces: {r['double_space']}; with leading/trailing spaces: {r['padded']}; compositions with double spaces: {r['comp_double_space']}")
        cur.execute("SELECT medicine_id, medicine_name FROM Medicines WHERE medicine_name LIKE '%  %' LIMIT 5")
        rep.sample("names_double_space", cur.fetchall(), ["medicine_id", "medicine_name"])

        # ---- 3. strength -------------------------------------------------------------------
        rep.section("3. Missing or invalid strengths")
        cur.execute("SELECT medicine_id, medicine_name, strength, composition, form FROM Medicines")
        rows = cur.fetchall()
        blank = [x for x in rows if not x["strength"] or x["strength"].strip().upper() in ("NA", "N/A", "")]
        unparsable = [x for x in rows if x["strength"] and x["strength"].strip().upper() not in ("NA", "N/A", "") and not STRENGTH_OK_RE.match(x["strength"].strip())]
        spaced = [x for x in rows if x["strength"] and re.search(r"\d\s+(?:mg|mcg|g|gm|ml|iu)\b", x["strength"], re.IGNORECASE)]
        mismatch = []
        for x in rows:
            nums = ingredient_numerators(x["composition"])
            first = re.match(r"\s*(\d+(?:\.\d+)?)", x["strength"] or "")
            if nums and first and float(first.group(1)) != float(nums[0]):
                mismatch.append(x)
        rep.line(f"strength blank or 'NA': {len(blank)} ({len(blank)/total:.1%})")
        rep.line(f"strength present but not in a recognisable '<number><unit>' form: {len(unparsable)}")
        rep.line(f"strength written with a space ('650 mg'), which breaks exact-string comparison: {len(spaced)}")
        rep.line(f"strength column disagrees with the first number in composition: {len(mismatch)}")
        rep.sample("strength_blank", blank, ["medicine_id", "medicine_name", "strength", "composition"])
        rep.sample("strength_unparsable", unparsable, ["medicine_id", "medicine_name", "strength"])
        rep.sample("strength_spaced", spaced, ["medicine_id", "medicine_name", "strength"])
        rep.sample("strength_mismatch", mismatch, ["medicine_id", "medicine_name", "strength", "composition"])

        # ---- 4. form -----------------------------------------------------------------------
        rep.section("4. Dosage form")
        cur.execute("SELECT form, COUNT(*) n FROM Medicines GROUP BY form ORDER BY n DESC")
        forms = cur.fetchall()
        null_forms = next((f["n"] for f in forms if f["form"] is None), 0)
        rep.line(f"form missing (NULL): {null_forms}")
        names = {str(f["form"]).lower(): f["n"] for f in forms if f["form"]}
        rep.line("synonym pairs present: Drop/Drops = %s/%s ; Eye Drop = %s ; Liquid/Solution/Syrup = %s/%s/%s" % (
            names.get("drop", 0), names.get("drops", 0), names.get("eye drop", 0), names.get("liquid", 0), names.get("solution", 0), names.get("syrup", 0)))

        # ---- 5. composition completeness ------------------------------------------------------
        rep.section("5. Composition completeness")
        cur.execute("SELECT medicine_id, medicine_name, composition FROM Medicines")
        incomplete = []
        for x in cur.fetchall():
            if THREE_STRENGTHS_RE.search(x["medicine_name"] or "") and len(split_ingredients(x["composition"])) <= 2:
                incomplete.append(x)
        rep.line(f"products whose NAME shows 3+ strengths (e.g. 100mg/325mg/250mg) but whose composition lists at most 2 ingredients: {len(incomplete)}")
        rep.line("  cause: the source CSV has only two composition columns (short_composition1/2), so a third ingredient is lost at import")
        rep.sample("composition_truncated", incomplete, ["medicine_id", "medicine_name", "composition"])

        # ---- 6. prices -----------------------------------------------------------------------
        rep.section("6. Suspicious prices")
        cur.execute("""SELECT SUM(price IS NULL) nulls, SUM(price = 0) zeros, SUM(price < 0) negs, SUM(price >= 100000) huge, MIN(price) lo, MAX(price) hi FROM Medicines""")
        p = cur.fetchone()
        rep.line(f"NULL: {p['nulls']}, zero: {p['zeros']}, negative: {p['negs']}, 100,000 or more: {p['huge']}; range Rs {p['lo']} to Rs {p['hi']}")
        cur.execute("SELECT medicine_id, medicine_name, price FROM Medicines WHERE price = 0 OR price >= 100000 ORDER BY price DESC LIMIT 12")
        rep.sample("price_extremes", cur.fetchall(), ["medicine_id", "medicine_name", "price"], show=6)

        cur.execute("""SELECT medicine_id, medicine_name, primary_salt, secondary_salt, strength, form, release_type, price, pack_size
                       FROM Medicines WHERE is_discontinued = 0 AND price > 0 AND primary_salt IS NOT NULL""")
        groups = collections.defaultdict(list)
        for x in cur.fetchall():
            groups[(x["primary_salt"], x["secondary_salt"], x["strength"], x["form"], x["release_type"])].append(x)
        spread20 = spread50 = tested = 0
        outliers = []
        for key, members in groups.items():
            if len(members) < 5:
                continue
            tested += 1
            prices = sorted(float(m["price"]) for m in members)
            if prices[-1] / prices[0] >= 20:
                spread20 += 1
            if prices[-1] / prices[0] >= 50:
                spread50 += 1
            med = statistics.median(prices)
            for m in members:
                ratio = float(m["price"]) / med
                if ratio >= 20 or ratio <= 1 / 20:
                    outliers.append({**m, "group_median": round(med, 2), "ratio_to_median": round(ratio, 2), "group_size": len(members)})
        rep.line(f"comparable groups with 5+ live products: {tested}")
        rep.line(f"  groups whose cheapest and dearest differ by 20x or more: {spread20}; by 50x or more: {spread50}")
        rep.line(f"  individual products priced 20x above or below their group's median: {len(outliers)}")
        outliers.sort(key=lambda o: -max(o["ratio_to_median"], 1 / max(o["ratio_to_median"], 1e-9)))
        rep.sample("price_outliers", outliers, ["medicine_name", "strength", "form", "price", "pack_size", "group_median", "ratio_to_median", "group_size"])
        rep.line("  these are rows to REVIEW, not proven errors: a pack of 1 vial and a pack of 100 tablets are priced very differently by design")

        # ---- 6b. the extreme-price rule the app applies (app/services/price_quality.py) -----------
        rep.section("6b. Extreme-price rule (flagged in the app, never deleted)")
        cur.execute("""SELECT medicine_id, medicine_name, manufacturer, primary_salt, secondary_salt, strength, form, release_type,
                              composition, price, pack_size
                       FROM Medicines WHERE is_discontinued = 0 AND price > 0 AND composition_incomplete = 0 AND primary_salt IS NOT NULL""")
        comparable = collections.defaultdict(list)
        for x in cur.fetchall():
            comparable[(x["primary_salt"], x["secondary_salt"], x["strength"], x["form"], x["release_type"], composition_key(x["composition"]))].append(x)
        flagged, judged_groups, judged_products, generic_total, generic_flagged = [], 0, 0, 0, 0
        GENERIC_MAKERS = ("davaindia", "genericart", "stayhappi", "danavish", "jan aushadhi")
        for members in comparable.values():
            stats = price_quality.group_stats([(m["price"], m["pack_size"]) for m in members])
            if not stats:
                continue
            judged_groups += 1
            for m in members:
                if price_quality.unit_price(m["price"], m["pack_size"]) is None or price_quality.parse_pack(m["pack_size"])[1] != stats["kind"]:
                    continue
                judged_products += 1
                is_generic = any(g in (m["manufacturer"] or "").lower() or g in (m["medicine_name"] or "").lower() for g in GENERIC_MAKERS)
                generic_total += is_generic
                flag = price_quality.classify(m["price"], m["pack_size"], stats)
                if flag:
                    generic_flagged += is_generic
                    unit = price_quality.unit_price(m["price"], m["pack_size"])
                    flagged.append({**m, "flag": flag, "unit_price": round(unit, 3), "group_median_unit": round(stats["median_unit"], 3), "group_size": stats["n"]})
        low = sum(1 for f in flagged if f["flag"] == price_quality.FLAG_LOW)
        rep.line(f"groups large enough to judge (>= {price_quality.MIN_GROUP_SIZE} priced products): {judged_groups}; products judged: {judged_products}")
        rep.line(f"flagged unusually LOW (unit price < 1/{price_quality.EXTREME_RATIO:g} of the group median): {low}; unusually HIGH: {len(flagged) - low}")
        rep.line(f"flag rate overall: {len(flagged) / max(judged_products, 1):.2%}; among generic-label products (DavaIndia, Genericart, ...): "
                 f"{generic_flagged}/{generic_total} = {generic_flagged / max(generic_total, 1):.2%}")
        rep.line("  (a rule that mostly flagged real low-cost generics would be over-flagging; the two rates should be similar)")
        flagged.sort(key=lambda f: f["unit_price"] / f["group_median_unit"] if f["flag"] == price_quality.FLAG_LOW else -f["unit_price"] / f["group_median_unit"])
        rep.sample("price_rule_flagged", flagged, ["medicine_name", "strength", "form", "price", "pack_size", "unit_price", "group_median_unit", "flag"])

        # ---- 6c. unit typos --------------------------------------------------------------------
        rep.section("6c. Strength units that disagree between products of the same medicine")
        cur.execute("SELECT medicine_id, medicine_name, composition FROM Medicines WHERE composition LIKE '%mcg%' OR composition LIKE '%mg%'")
        by_numbers = collections.defaultdict(lambda: collections.defaultdict(list))
        for x in cur.fetchall():
            parts = split_ingredients(x["composition"])
            if not parts:
                continue
            numbers = tuple((n, tuple(nums[:1])) for n, nums in parts)
            units = tuple(re.findall(r"\d(?:\.\d+)?\s*(mcg|mg|g|gm|iu|ml)", x["composition"] or "", re.IGNORECASE))
            by_numbers[numbers][tuple(u.lower() for u in units)].append(x)
        conflicts = []
        for numbers, unit_sets in by_numbers.items():
            if len(unit_sets) > 1:
                rare = min(unit_sets.values(), key=len)
                total = sum(len(v) for v in unit_sets.values())
                if len(rare) <= 0.05 * total:
                    conflicts.extend({"medicine_id": r["medicine_id"], "medicine_name": r["medicine_name"], "composition": r["composition"]} for r in rare)
        rep.line(f"products whose composition uses a unit used by under 5% of products with the same ingredients and numbers (probable typos, e.g. 500mcg for 500mg): {len(conflicts)}")
        rep.sample("unit_conflicts", conflicts, ["medicine_id", "medicine_name", "composition"])

        # ---- 7. pack size & dates ----------------------------------------------------------------
        rep.section("7. Pack size, status and dates")
        cur.execute("""SELECT SUM(pack_size IS NULL OR pack_size = '') missing_pack,
                              SUM(pack_size NOT REGEXP 'of [0-9]') no_quantity,
                              SUM(is_discontinued = 1) discontinued,
                              COUNT(DISTINCT DATE(imported_at)) import_days, MIN(imported_at) first_import, MAX(imported_at) last_import FROM Medicines""")
        d = cur.fetchone()
        rep.line(f"pack_size missing: {d['missing_pack']}; without a readable quantity: {d['no_quantity']}; discontinued: {d['discontinued']}")
        rep.line(f"all prices carry import date(s): {d['first_import']} to {d['last_import']} ({d['import_days']} distinct day(s)) - there is no per-row 'price as of' date from the source")

        rep.section("What to do with this (nothing was changed)")
        rep.line("Review the CSVs (--csv DIR). Clean at IMPORT time (normalise spacing/forms, flag rather than delete suspect rows) so the source data stays intact.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", metavar="DIR", help="write the full sample lists as CSV files into DIR")
    run(parser.parse_args().csv)
