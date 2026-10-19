"""
The data-source registry (Objective 6): every figure it states is counted from the live tables, a licence the repository does not
record is stored as NULL (never assumed), and registering never touches a medicine, an interaction or a pharmacy feed.
"""
import unittest
import uuid
from datetime import date

from tests import helpers


class Registry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from app.db import get_connection
        from app.services import data_sources_service
        cls.svc = data_sources_service
        cls.conn = get_connection()
        cls.cur = cls.conn.cursor()
        cls.rows = {r["source_key"]: r for r in data_sources_service.build_registry_rows(cls.cur, date.today().isoformat())}

    @classmethod
    def tearDownClass(cls):
        cls.cur.close()
        cls.conn.close()
        cls.ctx.pop()

    def one(self, sql):
        self.cur.execute(sql)
        return self.cur.fetchone()[0]

    def test_record_counts_are_the_live_table_counts(self):
        self.assertEqual(self.rows["indian_medicine_dataset"]["record_count"], self.one("SELECT COUNT(*) FROM Medicines"))
        self.assertEqual(self.rows["ddinter_2"]["record_count"], self.one("SELECT COUNT(*) FROM Drug_Interactions"))

    def test_the_quality_notes_quote_the_live_counts(self):
        notes = self.rows["indian_medicine_dataset"]["notes"]
        incomplete = self.one("SELECT COUNT(*) FROM Medicines WHERE composition_incomplete = 1")
        combos = self.one("SELECT COUNT(*) FROM Medicines WHERE secondary_salt IS NOT NULL AND secondary_salt <> ''")
        unpriced = self.one("SELECT COUNT(*) FROM Medicines WHERE price IS NULL OR price <= 0")
        for number in (incomplete, combos, unpriced):
            self.assertIn(f"{number:,}", notes)
        self.assertIn("never offered as an equivalent", notes)
        self.assertIn("not presented as clinically verified", notes)
        self.assertIn("not live prices", notes)

    def test_the_interaction_note_states_the_salt_coverage_it_measured(self):
        cover = self.svc.measure_salt_coverage(self.cur)
        self.assertGreater(cover["distinct_salts"], 1000)
        self.assertTrue(0 < cover["covered"] < cover["distinct_salts"])
        notes = self.rows["ddinter_2"]["notes"]
        self.assertIn(f"{cover['covered']:,} of the catalogue's {cover['distinct_salts']:,}", notes)
        self.assertIn(f"({cover['percent']}%)", notes)
        self.assertIn("never as safe", notes)

    def test_a_licence_is_recorded_only_where_the_repository_states_one(self):
        self.assertEqual(self.rows["indian_medicine_dataset"]["license"], "MIT (as stated by the source repository)")
        self.assertIsNone(self.rows["ddinter_2"]["license"])                      # not confirmed: stored as NULL, not assumed
        self.assertIn("not confirmed", self.rows["ddinter_2"]["notes"])

    def test_the_import_dates_are_the_real_import_dates(self):
        self.assertEqual(self.rows["indian_medicine_dataset"]["retrieved_at"], self.one("SELECT MIN(imported_at) FROM Medicines"))
        self.assertEqual(self.rows["ddinter_2"]["retrieved_at"], self.one("SELECT MIN(imported_at) FROM Drug_Interactions"))

    def test_the_real_registry_is_filled_and_the_two_sources_are_there(self):
        keys = {s["source_key"]: s for s in self.svc.list_sources()}
        self.assertIn("indian_medicine_dataset", keys)
        self.assertIn("ddinter_2", keys)
        self.assertFalse(keys["ddinter_2"]["license_recorded"])
        self.assertIsNone(keys["ddinter_2"]["license"])
        self.assertTrue(keys["indian_medicine_dataset"]["license_recorded"])

    def test_registering_refreshes_by_key_and_never_duplicates(self):
        key = f"zz_test_{uuid.uuid4().hex[:8]}"
        row = {"source_key": key, "name": "Test source", "kind": "reference_dataset", "url": None, "license": None, "record_count": 5, "retrieved_at": None, "notes": "first"}
        try:
            self.svc.register([row])
            self.svc.register([{**row, "record_count": 9, "notes": "second"}])
            listed = [s for s in self.svc.list_sources() if s["source_key"] == key]
            self.assertEqual(len(listed), 1)
            self.assertEqual((listed[0]["record_count"], listed[0]["notes"], listed[0]["license_recorded"]), (9, "second", False))
        finally:
            from app.models.offer_model import delete_source
            delete_source(key)


class ThroughTheApi(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.client = self.app.test_client()
        self.key = f"zz_test_{uuid.uuid4().hex[:8]}"

    def tearDown(self):
        with self.app.app_context():
            from app.models.offer_model import delete_source
            delete_source(self.key)

    def test_the_list_is_public_and_carries_the_registry(self):
        r = self.client.get("/api/data-sources")                                    # no token: nothing here is personal
        self.assertEqual(r.status_code, 200)
        keys = {s["source_key"]: s for s in r.get_json()["sources"]}
        self.assertEqual(keys["ddinter_2"]["license"], None)
        self.assertFalse(keys["ddinter_2"]["license_recorded"])
        self.assertGreater(keys["indian_medicine_dataset"]["record_count"], 250000)
        self.assertIsNone(keys["indian_medicine_dataset"]["pharmacies"])           # counts apply to pharmacy feeds only

    def test_a_pharmacy_feed_appears_with_its_counts_and_the_demo_label(self):
        from datetime import datetime, timedelta
        from app.services.feed_import_service import import_feed
        header = ["pharmacy", "city", "medicine_name", "pack_size", "price", "availability", "quantity", "observed_at"]
        when = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        with self.app.app_context():
            import_feed([(2, dict(zip(header, ("Demo Pharmacy", "City", "Dolo 650 Tablet", "", "30", "in_stock", "", when))))], self.key, "Demo feed", kind="synthetic_demo")
        feed = next(s for s in self.client.get("/api/data-sources").get_json()["sources"] if s["source_key"] == self.key)
        self.assertEqual((feed["demo"], feed["pharmacies"], feed["observations"], feed["kind"]), (True, 1, 1, "synthetic_demo"))
        self.assertFalse(feed["license_recorded"])


class Script(unittest.TestCase):
    def test_the_script_runs_and_leaves_the_registry_consistent(self):
        import os
        import subprocess
        import sys
        backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run([sys.executable, os.path.join("database", "register_data_sources.py")], cwd=backend, capture_output=True, text=True, encoding="utf-8", timeout=180)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ddinter_2:", result.stdout)
        self.assertIn("licence: not recorded", result.stdout)
        self.assertIn("MIT (as stated by the source repository)", result.stdout)


if __name__ == "__main__":
    unittest.main()
