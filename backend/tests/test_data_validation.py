"""
Objective 6: checking the medicine data against itself, and saying which outside services are configured.

A note from the validator is a reason to look twice. It is never a correction, and agreement between fields of one community dataset is not
clinical verification; these tests pin down exactly what is, and is not, flagged.
"""
import unittest
from unittest import mock

from tests import helpers


def product(name, composition, **over):
    base = {"medicine_name": name, "composition": composition, "form": "Tablet", "strength": "500mg", "pack_size": "strip of 10 tablets", "price": 25.0,
            "composition_incomplete": False}
    base.update(over)
    return base


class Rules(unittest.TestCase):
    def setUp(self):
        from app.services import data_validation_service
        self.v = data_validation_service

    def codes(self, row):
        return [n["code"] for n in self.v.validate_medicine(row)]

    def test_a_product_whose_fields_agree_has_no_notes(self):
        self.assertEqual(self.codes(product("Amoxycillin 500mg Tablet", "Amoxycillin (500mg)")), [])

    def test_a_strength_in_the_name_that_matches_no_ingredient_is_noted(self):
        self.assertEqual(self.codes(product("Foo 250mg Tablet", "Foo (500mg)")), ["strength_not_in_composition"])

    def test_the_total_of_the_ingredients_and_other_units_explain_a_strength(self):
        cases = [
            ("Augmentin 625mg Tablet", "Amoxycillin (500mg) + Clavulanic Acid (125mg)"),          # the total
            ("Ampoxin 1gm Injection", "Ampicillin (500mg) + Cloxacillin (500mg)"),                # two equal ingredients, in grams
            ("Augmentin 1.2gm Injection", "Amoxycillin (1000mg) + Clavulanic Acid (200mg)"),
            ("Vitamin D3 60000 IU Capsule", "Cholecalciferol (60000IU)"),
            ("Cyanocobalamin 1500mcg Tablet", "Methylcobalamin (1.5mg)"),                         # mcg against mg
            ("Albumin 20% Solution", "Albumin (20%)"),
            ("Drug 100mg/325mg Tablet", "Drug (100mg) + Other (325mg)"),
        ]
        for name, composition in cases:
            self.assertNotIn("strength_not_in_composition", self.codes(product(name, composition, form="Tablet" if "Tablet" in name else "Injection")), name)

    def test_units_are_not_confused_across_kinds(self):
        self.assertIn("strength_not_in_composition", self.codes(product("Foo 500 IU Tablet", "Foo (500mg)")))
        self.assertIn("strength_not_in_composition", self.codes(product("Foo 5% Tablet", "Foo (5mg)")))

    def test_a_bare_number_in_a_brand_name_is_not_checked(self):
        self.assertEqual(self.codes(product("Pan 40 Tablet", "Pantoprazole (40mg)")), [])
        self.assertEqual(self.codes(product("Becosules 5 Tablet", "Foo (9mg)")), [])
        self.assertEqual(self.codes(product("Dolo 650 Tablet", "Paracetamol (500mg)")), [])

    def test_missing_values_are_noted_including_the_texts_the_source_uses_for_missing(self):
        for blank in (None, "", "  ", "NA", "n/a", "NaN", "none", "-"):
            codes = self.codes(product("Foo Tablet", "Foo (5mg)", strength=blank, pack_size=blank, form=blank))
            for expected in ("no_strength", "no_pack_size", "no_form"):
                self.assertIn(expected, codes, repr(blank))
        self.assertIn("no_composition", self.codes(product("Foo Tablet", "")))
        self.assertIn("no_composition", self.codes(product("Foo Tablet", None)))

    def test_prices(self):
        for price in (None, 0, -3):
            self.assertIn("no_usable_price", self.codes(product("Foo Tablet", "Foo (5mg)", price=price)))
        self.assertNotIn("no_usable_price", self.codes(product("Foo Tablet", "Foo (5mg)", price=0.5)))

    def test_an_incomplete_ingredient_list_is_noted(self):
        self.assertIn("ingredient_list_incomplete", self.codes(product("Acimol MR 100mg/325mg/250mg Tablet", "A (100mg) + B (325mg)", composition_incomplete=True)))

    def test_a_name_that_points_to_another_form_than_the_record_is_noted(self):
        self.assertIn("form_disagrees_with_name", self.codes(product("Foo Syrup", "Foo (5mg)", form="Tablet")))
        self.assertNotIn("form_disagrees_with_name", self.codes(product("Foo Tablet", "Foo (5mg)", form="Tablet")))
        self.assertNotIn("form_disagrees_with_name", self.codes(product("Foo", "Foo (5mg)", form="Tablet")))

    def test_each_note_has_a_level_and_plain_text_and_the_wording_never_claims_a_correction(self):
        # two products between them trigger every note (one row cannot both lack a form and disagree about it)
        a = self.v.validate_medicine(product("Foo 250mg Syrup", None, form="Tablet", strength="NA", pack_size="", price=0, composition_incomplete=True))
        b = self.v.validate_medicine(product("Foo 250mg Tablet", "Foo (500mg)", form=None))
        everything = a + b
        self.assertEqual({n["code"] for n in everything}, set(self.v.NOTES))
        for note in everything:
            self.assertIn(note["level"], ("warn", "info"))
            self.assertTrue(note["text"].endswith("."))
            self.assertNotRegex(note["text"], r"(?i)\bwrong\b|\bincorrect\b|\bcorrected?\b|\bverified\b")
        self.assertTrue(all(n["level"] == "warn" for n in self.v.data_notes(product("Foo 250mg Syrup", None, strength="NA"), warn_only=True)))

    def test_it_never_changes_the_row_it_checks(self):
        row = product("Foo 250mg Tablet", "Foo (500mg)")
        before = dict(row)
        self.v.validate_medicine(row)
        self.assertEqual(row, before)

    def test_missing_keys_count_as_missing_values_not_errors(self):
        self.assertIn("no_composition", self.codes({"medicine_name": "Foo"}))


class AgainstTheRealCatalogue(unittest.TestCase):
    """The real table: the scan counts agree with what the SQL says, and a row is only flagged for a reason a person can see."""

    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from app.db import get_connection
        from app.services import data_validation_service
        cls.v = data_validation_service
        cls.conn = get_connection()
        cursor = cls.conn.cursor()
        cls.report = data_validation_service.scan_table(cursor, examples=5, limit=20000)
        cursor.close()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        cls.ctx.pop()

    def count(self, sql):
        cursor = self.conn.cursor()
        cursor.execute(sql)
        value = cursor.fetchone()[0]
        cursor.close()
        return value

    def test_the_scan_checks_every_row_it_is_given_and_counts_consistently(self):
        self.assertEqual(self.report["checked"], 20000)
        self.assertLessEqual(self.report["with_notes"], 20000)
        self.assertLessEqual(max(f["count"] for f in self.report["by_code"].values()), self.report["with_notes"])

    def test_counts_agree_with_the_database_for_the_same_rows(self):
        missing = "('', 'na', 'n/a', 'nan', 'none', 'null', '-')"
        sql_strength = self.count(
            f"SELECT COUNT(*) FROM (SELECT strength FROM Medicines LIMIT 20000) t WHERE strength IS NULL OR LOWER(TRIM(strength)) IN {missing}")
        sql_price = self.count("SELECT COUNT(*) FROM (SELECT price FROM Medicines LIMIT 20000) t WHERE price IS NULL OR price <= 0")
        sql_incomplete = self.count("SELECT COUNT(*) FROM (SELECT composition_incomplete c FROM Medicines LIMIT 20000) t WHERE c = 1")
        self.assertEqual(self.report["by_code"]["no_strength"]["count"], sql_strength)
        self.assertEqual(self.report["by_code"]["no_usable_price"]["count"], sql_price)
        self.assertEqual(self.report["by_code"]["ingredient_list_incomplete"]["count"], sql_incomplete)

    def test_every_example_really_has_the_note_it_is_listed_under(self):
        for code, found in self.report["by_code"].items():
            for example in found["examples"]:
                cursor = self.conn.cursor(dictionary=True)
                cursor.execute("SELECT * FROM Medicines WHERE medicine_id = %s", (example["medicine_id"],))
                row = cursor.fetchone()
                cursor.close()
                self.assertIn(code, [n["code"] for n in self.v.validate_medicine(row)], (code, example))

    def test_the_registry_and_the_validator_use_the_same_definition_of_missing(self):
        from app.services import data_sources_service
        cursor = self.conn.cursor()
        measured = data_sources_service.measure_medicines(cursor)
        cursor.close()
        self.assertEqual(measured["without_a_strength"], self.count(
            "SELECT COUNT(*) FROM Medicines WHERE strength IS NULL OR LOWER(TRIM(strength)) IN ('', 'na', 'n/a', 'nan', 'none', 'null', '-')"))


class ThroughTheScreens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.client = cls.app.test_client()
        cls.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        with cls.app.app_context():
            cls.uid = cls.accounts.user(allergies=[])
            cls.h = {"Authorization": f"Bearer {create_access_token(identity=str(cls.uid))}"}

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.accounts.cleanup()

    def test_search_results_carry_their_data_notes(self):
        rows = self.client.get("/api/medicines/search?q=Adrenaline Tartrate", headers=self.h).get_json()["medicines"]
        self.assertTrue(rows)
        self.assertTrue(all("data_notes" in r for r in rows))
        flagged = [r for r in rows if r["strength"] in (None, "", "NA")]
        self.assertTrue(flagged)
        self.assertIn("no_strength", [n["code"] for n in flagged[0]["data_notes"]])

    def test_an_identified_line_carries_its_notes_and_an_unconfirmed_one_none(self):
        with self.app.app_context():
            pid = self.accounts.prescription(self.uid)
            self.accounts.line(pid, "Adrenaline Tartrate Injection", raw_text="Inj Adrenaline Tartrate", confidence=0.99)
            self.accounts.line(pid, None, raw_text="Tab Unknownmed", status="needs_verification", confidence=None)
        body = self.client.get(f"/api/prescriptions/{pid}", headers=self.h).get_json()
        by_raw = {m["raw_text"]: m for m in body["detected_medicines"]}
        self.assertIn("no_strength", [n["code"] for n in by_raw["Inj Adrenaline Tartrate"]["data_notes"]])
        self.assertEqual(by_raw["Tab Unknownmed"]["data_notes"], [])

    def test_the_pdf_prints_the_warning_level_data_notes_of_an_identified_medicine(self):
        import os
        import shutil
        import tempfile
        import pypdfium2 as pdfium
        from app.models.prescription_model import get_prescription_by_id
        from app.services.smart_report_service import build_report_pdf
        with self.app.app_context():
            pid = self.accounts.prescription(self.uid)
            # a real product whose name states a percentage while its ingredient list is in milligrams: the two cannot be reconciled from the data
            self.accounts.line(pid, "Anasure 2% Solution", raw_text="Anasure 2% Solution", confidence=0.99)
            tmp = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, tmp, True)
            path = os.path.join(tmp, "r.pdf")
            build_report_pdf(pid, get_prescription_by_id(pid), path)
        doc = pdfium.PdfDocument(path)
        text = " ".join(" ".join(doc[i].get_textpage().get_text_range() for i in range(len(doc))).split())
        doc.close()
        self.assertIn("Data note: The strength in the name could not be matched to the ingredient strengths on record", text)


class ExternalServices(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        from app.services import data_sources_service
        self.d = data_sources_service

    def tearDown(self):
        self.ctx.pop()

    def by_key(self):
        return {s["key"]: s for s in self.d.external_services()}

    def test_each_service_says_whether_it_is_configured_and_what_happens_without_it(self):
        services = self.by_key()
        self.assertEqual(set(services), {"google_vision", "gemini", "openstreetmap", "pharmacy_feeds"})
        for s in services.values():
            self.assertIsInstance(s["configured"], bool)
            self.assertTrue(s["when_unavailable"].endswith("."))
        self.assertIn("EasyOCR", services["google_vision"]["when_unavailable"])
        self.assertIn("never shows an empty list", services["openstreetmap"]["when_unavailable"])

    def test_configuration_follows_the_settings_and_no_key_is_ever_shown(self):
        with mock.patch("app.config.Config.GEMINI_API_KEY", "a-secret-key-that-must-not-appear"), mock.patch("app.config.Config.GOOGLE_VISION_API_KEY", ""), \
             mock.patch("app.config.Config.PLACES_PROVIDER", "off"):
            services = self.by_key()
            shown = repr(self.d.external_services())
        self.assertTrue(services["gemini"]["configured"])
        self.assertFalse(services["google_vision"]["configured"])
        self.assertFalse(services["openstreetmap"]["configured"])
        self.assertNotIn("a-secret-key-that-must-not-appear", shown)

    def test_the_route_is_public_and_carries_the_statuses_and_no_secret(self):
        body = self.client.get("/api/data-sources").get_json()
        self.assertEqual({s["key"] for s in body["external_services"]}, {"google_vision", "gemini", "openstreetmap", "pharmacy_feeds"})
        from app.config import Config
        text = repr(body)
        for secret in (Config.GOOGLE_VISION_API_KEY, Config.GEMINI_API_KEY):
            if secret:
                self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
