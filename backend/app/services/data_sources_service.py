"""
What data PharmaCompare uses, where it came from, and how good it is - measured, not asserted.

The registry (Data_Sources) is filled by database/register_data_sources.py from the live tables and from what database/PROVENANCE.md
records. A licence that the repository does not record is stored as NULL and shown as "not recorded": it is never assumed.
"""
from app.db import get_connection

SOURCE_MEDICINES = "indian_medicine_dataset"
SOURCE_INTERACTIONS = "ddinter_2"
MISSING_SQL = "('', 'na', 'n/a', 'nan', 'none', 'null', '-')"


def measure_medicines(cursor):
    """Quality figures of the Medicines table, counted now."""
    def one(sql):
        cursor.execute(sql)
        return cursor.fetchone()[0]

    total = one("SELECT COUNT(*) FROM Medicines")
    return {
        "products": total,
        "without_a_usable_price": one("SELECT COUNT(*) FROM Medicines WHERE price IS NULL OR price <= 0"),
        # the source writes a missing value as text ("NA"), so that counts as missing too (the same rule as data_validation_service)
        "without_a_strength": one(f"SELECT COUNT(*) FROM Medicines WHERE strength IS NULL OR LOWER(TRIM(strength)) IN {MISSING_SQL}"),
        "without_a_pack_size": one(f"SELECT COUNT(*) FROM Medicines WHERE pack_size IS NULL OR LOWER(TRIM(pack_size)) IN {MISSING_SQL}"),
        "ingredient_list_incomplete": one("SELECT COUNT(*) FROM Medicines WHERE composition_incomplete = 1"),
        "combination_products": one("SELECT COUNT(*) FROM Medicines WHERE secondary_salt IS NOT NULL AND secondary_salt <> ''"),
        "discontinued": one("SELECT COUNT(*) FROM Medicines WHERE is_discontinued = 1"),
        "modified_release": one("SELECT COUNT(*) FROM Medicines WHERE release_type IS NOT NULL"),
        "imported_first": one("SELECT MIN(imported_at) FROM Medicines"),
    }


def measure_interactions(cursor):
    cursor.execute("SELECT severity, COUNT(*) FROM Drug_Interactions GROUP BY severity")
    by_severity = {severity: n for severity, n in cursor.fetchall()}
    cursor.execute("SELECT COUNT(*) FROM Drug_Interactions")
    pairs = cursor.fetchone()[0]
    cursor.execute("SELECT MIN(imported_at) FROM Drug_Interactions")
    imported = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM (SELECT drug_a_norm AS d FROM Drug_Interactions UNION SELECT drug_b_norm FROM Drug_Interactions) t")
    substances = cursor.fetchone()[0]
    return {"pairs": pairs, "by_severity": by_severity, "substances": substances, "imported_first": imported}


def measure_salt_coverage(cursor):
    """
    The share of the catalogue's distinct primary salts that the interaction data tracks (exact name, then the salt-form-normalised name).
    A salt outside this coverage can never be checked, which the app reports as "interaction data not available".
    """
    from app.services.clinical_decision_service import _normalize_salt

    cursor.execute("SELECT DISTINCT primary_salt FROM Medicines WHERE primary_salt IS NOT NULL AND primary_salt <> ''")
    salts = [r[0] for r in cursor.fetchall()]
    cursor.execute("SELECT drug_a_norm FROM Drug_Interactions UNION SELECT drug_b_norm FROM Drug_Interactions")
    tracked = {r[0] for r in cursor.fetchall()}
    covered = sum(1 for s in salts if s.strip().lower() in tracked or _normalize_salt(s) in tracked)
    return {"distinct_salts": len(salts), "covered": covered, "percent": round(covered * 100.0 / len(salts), 1) if salts else None}


def measure_validation(cursor):
    """The product-by-product consistency check (see data_validation_service), counted now, as one sentence for the registry."""
    from app.services import data_validation_service
    report = data_validation_service.scan_table(cursor, examples=0)
    c = {code: found["count"] for code, found in report["by_code"].items()}
    return (
        f"Consistency check of each product against its own fields: {report['with_notes']:,} of {report['checked']:,} products have at least one note "
        f"({c['strength_not_in_composition']:,} with a strength in the name that could not be matched to the ingredient strengths, "
        f"{c['ingredient_list_incomplete']:,} with an incomplete ingredient list, {c['no_strength']:,} with no strength, {c['no_form']:,} with no form, "
        f"{c['no_usable_price']:,} with no usable price; the form never disagreed with the name because it was derived from the name at import). "
        "A note is a reason to look twice, not a correction: agreement between fields of one community dataset is not clinical verification."
    )


def build_registry_rows(cursor, today):
    """The two reference sources, from the live tables. Returns [dict] ready for registration."""
    m = measure_medicines(cursor)
    i = measure_interactions(cursor)
    cover = measure_salt_coverage(cursor)
    medicines_notes = (
        f"Quality check on {today}: {m['products']:,} products. {m['without_a_usable_price']:,} have no usable price, "
        f"{m['without_a_strength']:,} no strength, {m['without_a_pack_size']:,} no pack size. "
        f"{m['ingredient_list_incomplete']:,} have an incomplete ingredient list (the source holds two ingredient columns, so a third was lost) "
        f"and are never offered as an equivalent. {m['combination_products']:,} are combination products "
        f"(the strength column holds only the first ingredient's strength, so the app shows every ingredient's strength from the composition). "
        f"{m['discontinued']:,} are marked discontinued and {m['modified_release']:,} are modified-release. "
        "Compiled by a community project; the repository does not say where the data was compiled from, so it is not presented as clinically "
        "verified or government-sourced. Prices are a snapshot from the import date, not live prices. " + measure_validation(cursor)
    )
    severity = ", ".join(f"{n:,} {name}" for name, n in sorted(i["by_severity"].items(), key=lambda kv: -kv[1]))
    interactions_notes = (
        f"Quality check on {today}: {i['pairs']:,} unique pairs over {i['substances']:,} substances ({severity}). "
        f"{cover['covered']:,} of the catalogue's {cover['distinct_salts']:,} distinct primary salts ({cover['percent']}%) are tracked here "
        "(exact or salt-form-normalised name); anything else is reported as interaction data not available, never as safe. "
        "Pair and severity only: no mechanism or management text. Severity is DDInter's own scale, kept as given. "
        "The licence and redistribution terms were not confirmed, so the source CSV files are not committed to the public repository."
    )
    return [
        {"source_key": SOURCE_MEDICINES, "name": "Indian Medicine Dataset (junioralive, GitHub)", "kind": "reference_dataset",
         "url": "https://github.com/junioralive/Indian-Medicine-Dataset", "license": "MIT (as stated by the source repository)",
         "record_count": m["products"], "retrieved_at": m["imported_first"], "notes": medicines_notes},
        {"source_key": SOURCE_INTERACTIONS, "name": "DDInter 2.0 drug-drug interactions", "kind": "interaction_dataset",
         "url": "https://ddinter2.scbdd.com/", "license": None,
         "record_count": i["pairs"], "retrieved_at": i["imported_first"], "notes": interactions_notes},
    ]


def register(rows):
    """Creates or refreshes the registry rows (matched on source_key). Pharmacy feeds are never touched here."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for r in rows:
            cursor.execute("SELECT source_id FROM Data_Sources WHERE source_key = %s", (r["source_key"],))
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE Data_Sources SET name=%s, kind=%s, url=%s, license=%s, record_count=%s, retrieved_at=%s, notes=%s WHERE source_key=%s",
                    (r["name"], r["kind"], r["url"], r["license"], r["record_count"], r["retrieved_at"], r["notes"], r["source_key"]),
                )
            else:
                cursor.execute(
                    "INSERT INTO Data_Sources (source_key, name, kind, url, license, record_count, retrieved_at, notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (r["source_key"], r["name"], r["kind"], r["url"], r["license"], r["record_count"], r["retrieved_at"], r["notes"]),
                )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def external_services():
    """
    The outside services the app can use, whether each is CONFIGURED (never the key), and what the app does without it. This says "configured",
    not "up": nothing here calls a service to check, and a service that is configured can still be down. Each failure is handled where the service
    is used (the OCR falls back to the local reader, the summary to a plain template, a store search says it could not be reached).
    """
    from app.config import Config
    return [
        {"key": "google_vision", "name": "Google Cloud Vision (reading prescription text)", "configured": bool(Config.GOOGLE_VISION_API_KEY),
         "when_unavailable": "The local EasyOCR reader is used instead. It is weaker on handwriting, so more lines will need verification."},
        {"key": "gemini", "name": "Google Gemini (plain-language summary and medicine explanation)", "configured": bool(Config.GEMINI_API_KEY),
         "when_unavailable": "A plain template summary is written from the same figures. Nothing is lost except the wording."},
        {"key": "openstreetmap", "name": "OpenStreetMap (store listings, place search and map)", "configured": Config.PLACES_PROVIDER == "osm_overpass",
         "when_unavailable": "The Stores page says the listing could not be reached. It never shows an empty list as if there were no stores."},
        {"key": "pharmacy_feeds", "name": "Pharmacy price and stock feeds", "configured": live_data()["live_feed_connected"],
         "when_unavailable": "Only reference prices are shown, and stock is shown as not known."},
    ]


def live_data():
    """Whether any pharmacy feed has delivered anything (see price_provenance_service.live_data_status)."""
    from app.services import price_provenance_service
    conn = get_connection()
    cursor = conn.cursor()
    try:
        return price_provenance_service.live_data_status(cursor)
    finally:
        cursor.close()
        conn.close()


def list_sources():
    """The registry as the About page shows it, with each pharmacy feed's pharmacy and observation counts."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT ds.source_key, ds.name, ds.kind, ds.url, ds.license, ds.record_count, ds.retrieved_at, ds.notes,
                      COUNT(DISTINCT ph.pharmacy_id) AS pharmacies, COUNT(o.offer_id) AS observations,
                      MAX(o.observed_at) AS latest_observed, MAX(o.imported_at) AS latest_received
               FROM Data_Sources ds
               LEFT JOIN Pharmacies ph ON ph.source_id = ds.source_id
               LEFT JOIN Pharmacy_Offers o ON o.pharmacy_id = ph.pharmacy_id
               GROUP BY ds.source_id
               ORDER BY FIELD(ds.kind, 'reference_dataset', 'interaction_dataset', 'pharmacy_feed', 'synthetic_demo'), ds.name"""
        )
        out = []
        for r in cursor.fetchall():
            feed = r["kind"] in ("pharmacy_feed", "synthetic_demo")
            out.append({
                "source_key": r["source_key"], "name": r["name"], "kind": r["kind"], "url": r["url"],
                "license": r["license"] or None, "license_recorded": bool(r["license"]),
                "record_count": r["record_count"], "retrieved_at": r["retrieved_at"].isoformat() if r["retrieved_at"] else None,
                "notes": r["notes"], "demo": r["kind"] == "synthetic_demo",
                "pharmacies": r["pharmacies"] if feed else None, "observations": r["observations"] if feed else None,
                # freshness of a feed: when the newest report was observed by the pharmacy, and when we last received data from it
                "latest_observed_at": r["latest_observed"].isoformat() if feed and r["latest_observed"] else None,
                "latest_received_at": r["latest_received"].isoformat() if feed and r["latest_received"] else None,
            })
        return out
    finally:
        cursor.close()
        conn.close()
