"""
Imports a pharmacy price / stock feed (a CSV a pharmacy or partner supplies) into Pharmacy_Offers.

  python database/import_pharmacy_feed.py FEED.csv --source-key acme_pharmacy --name "Acme Pharmacy feed" [--dry-run] [--rejects rejected.csv]
  python database/import_pharmacy_feed.py --remove-source acme_pharmacy

Strict by design (see app/services/feed_import_service.py): every row needs an observation time, a product that resolves to exactly
one catalogue entry, and a recognisable price and/or stock status. Rows that do not are written to the rejects file with the reason;
nothing is guessed. Re-importing the same file adds nothing (observations are unique per pharmacy, product and time).

Demo data: pass --kind synthetic_demo. It is stored under that kind and labelled "Demo data" everywhere the app shows it. Remove it
afterwards with --remove-source. Never import invented figures as kind pharmacy_feed.
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app.models import offer_model
from app.services import feed_import_service


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("feed", nargs="?", help="the CSV file to import")
    parser.add_argument("--source-key", help="a short stable id for this feed, e.g. acme_pharmacy")
    parser.add_argument("--name", help="the feed's display name")
    parser.add_argument("--kind", default="pharmacy_feed", choices=feed_import_service.KINDS)
    parser.add_argument("--url", help="where the feed comes from")
    parser.add_argument("--license", dest="license_text", help="the terms the feed was supplied under")
    parser.add_argument("--notes")
    parser.add_argument("--dry-run", action="store_true", help="validate everything, write nothing")
    parser.add_argument("--rejects", help="write the rejected rows and their reasons to this CSV file")
    parser.add_argument("--remove-source", metavar="SOURCE_KEY", help="delete a feed with its pharmacies and every observation")
    args = parser.parse_args(argv)

    if args.remove_source:
        pharmacies, offers = offer_model.counts_for_source(args.remove_source)
        removed = offer_model.delete_source(args.remove_source)
        print(f"removed {removed} source ({pharmacies} pharmacies, {offers} observations)")
        return 0
    if not (args.feed and args.source_key and args.name):
        parser.error("a feed file, --source-key and --name are required")

    rows = feed_import_service.read_csv(args.feed)
    report = feed_import_service.import_feed(
        rows, args.source_key, args.name, kind=args.kind, url=args.url, license_text=args.license_text, notes=args.notes, dry_run=args.dry_run,
    )
    verb = "would import" if report["dry_run"] else "imported"
    print(f"read {report['read']} rows | {verb} {report['imported']} | already present {report['duplicates']} | "
          f"rejected {len(report['rejected'])} | pharmacies {report['pharmacies']}")
    for line, reason, _ in report["rejected"][:10]:
        print(f"  line {line}: {reason}")
    if len(report["rejected"]) > 10:
        print(f"  ... and {len(report['rejected']) - 10} more")
    if args.rejects and report["rejected"]:
        with open(args.rejects, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["line", "reason"] + sorted({k for _, _, row in report["rejected"] for k in row}))
            columns = sorted({k for _, _, row in report["rejected"] for k in row})
            for line, reason, row in report["rejected"]:
                writer.writerow([line, reason] + [row.get(c, "") for c in columns])
        print(f"rejected rows written to {args.rejects}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
