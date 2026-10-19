"""
Creates, lists and revokes the API keys pharmacy partners use to push price and stock reports (POST /api/feeds/offers).

  python database/manage_partner_keys.py create --source-key acme_pharmacy --name "Acme Pharmacy feed" --label "main server"
  python database/manage_partner_keys.py list
  python database/manage_partner_keys.py revoke 3

`create` makes the pharmacy-feed source if it does not exist and prints the key ONCE: only its hash is stored, so a lost key cannot be recovered
and is replaced by creating a new one and revoking the old. Give the key to the partner over a safe channel. Nothing here contacts any partner.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app.db import get_connection
from app.models import offer_model, partner_key_model


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="make a key for a pharmacy feed (and the feed, if new)")
    create.add_argument("--source-key", required=True, help="a short stable id for the feed, e.g. acme_pharmacy")
    create.add_argument("--name", required=True, help="the feed's display name")
    create.add_argument("--label", required=True, help="what this key is for, e.g. 'main server'")
    create.add_argument("--url")
    create.add_argument("--license", dest="license_text")
    sub.add_parser("list", help="every key, without the secret")
    revoke = sub.add_parser("revoke", help="stop a key working")
    revoke.add_argument("key_id", type=int)
    args = parser.parse_args(argv)

    if args.command == "create":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT kind FROM Data_Sources WHERE source_key = %s", (args.source_key,))
        existing = cursor.fetchone()
        cursor.close()
        conn.close()
        if existing and existing[0] != "pharmacy_feed":
            print(f"refused: {args.source_key} is a {existing[0]} source, not a pharmacy feed")
            return 1
        source_id = offer_model.upsert_source(args.source_key, args.name, "pharmacy_feed", args.url, args.license_text)
        key_id, token = partner_key_model.create_key(source_id, args.label)
        print(f"key {key_id} created for {args.source_key}. Copy it now; it is not stored and cannot be shown again:\n\n  {token}\n")
        return 0
    if args.command == "list":
        rows = partner_key_model.list_keys()
        if not rows:
            print("no partner keys")
        for r in rows:
            state = "REVOKED" if r["revoked_at"] else "active"
            used = r["last_used_at"].strftime("%Y-%m-%d %H:%M") if r["last_used_at"] else "never used"
            print(f"{r['key_id']:>4}  {r['key_prefix']}...  {state:<8} {r['source_key']:<24} {r['label']:<24} {used}")
        return 0
    print("revoked" if partner_key_model.revoke(args.key_id) else "no live key with that id")
    return 0


if __name__ == "__main__":
    sys.exit(main())
