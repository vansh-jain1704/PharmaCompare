"""Matcher and alternatives tests against the real dataset."""
import unittest

from tests import helpers
from app.services.release_type import RELEASE_LABELS  # noqa: F401

SHOULD_MATCH = [  # (line, text expected inside the matched medicine name)
    ("Dolo 650", "Dolo 650"), ("Tab Dolo 650", "Dolo 650"), ("Dolo 650 Tablet", "Dolo 650"),
    ("Crocin Advance", "Crocin Advance"), ("Calpol 650mg Tablet", "Calpol 650"),
    ("Tab Paracetamol 650", "Paracetamol"), ("Tab Paracetamol 650mg", "Paracetamol"),
    ("Tab Azee 500", "Azee 500"), ("Azithral 500", "Azithral 500"), ("Pantop 40", "Pantop 40"),
    ("Pan-D", "Pan-D"), ("Pan D", "Pan-D"), ("Zerodol-P", "Zerodol-P"), ("Zerodol P", "Zerodol-P"),
    ("Zerodol-P Tablet", "Zerodol-P"), ("Augmentin 625 Duo", "Augmentin"),
    ("Telma 40", "Telma 40"), ("Ecosprin 75", "Ecosprin"), ("Tab Loperamide 2", "2mg Tablet"),
    ("Cap Amoxycillin 500", "Amoxycillin 500mg Capsule"), ("Amoxicillin 500mg Capsule", "Amoxycillin 500mg Capsule"),
    ("Tab Taxim-O 200", "Taxim-O 200"),
]
# Lines that name a medicine but not WHICH strength / form: the dataset holds several
# different medicines that fit, so the matcher must not pick one. Before this check
# "Taxim-O" became a 25 mg drops product and "Metformin" a 500 mg tablet.
NEEDS_CHOICE = [
    "Paracetamol 650", "Azee 500", "Montek LC", "Loperamide", "Amoxycillin", "Amoxicillin", "Taxim-O", "Metformin",
    "Augmentin", "Telma", "Atorvastatin", "Ibuprofen", "Syp Paracetamol", "Amoxicillin + Clavulanic acid",
    "Aceclofenac 100 + Paracetamol 325",
]
MUST_NOT_MATCH = [
    "Patient: Test Patient", "Dr. R Mehta, MBBS MD", "Cardiology", "Date: 09-09-2026",
    "General Hospital", "Age: 34 years", "Treatment :", "Tablet", "Capsule", "Syrup",
    "Diagnosis: Fever", "Follow up after 5 days",
]


def _ids(medicine):
    return medicine["medicine_id"] if medicine else None


class MatcherTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from app.services.medicine_matching_service import match_line
        cls.match = staticmethod(match_line)

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    # ---- regression benchmark ----------------------------------------------------------
    def test_known_medicines_still_match(self):
        failures = []
        for line, expect in SHOULD_MATCH:
            r = self.match(line)
            m = r["medicine"]
            if not (r["status"] == "matched" and m and expect.lower() in m["medicine_name"].lower()):
                failures.append((line, r["status"], m["medicine_name"] if m else None))
        self.assertEqual(failures, [], f"{len(SHOULD_MATCH) - len(failures)}/{len(SHOULD_MATCH)} matched")

    # ---- generic names: never pick a dose or form the line did not state ----------------
    def test_under_specified_lines_are_not_silently_matched(self):
        for line in NEEDS_CHOICE:
            r = self.match(line)
            self.assertEqual(r["status"], "needs_verification", line)
            self.assertIsNone(r["medicine"], f"{line}: must not name a product")
            self.assertIsNone(r["confidence"], line)
            self.assertTrue(r["needs_disambiguation"], line)
            self.assertGreaterEqual(len(r["options"]), 2, line)

    def test_options_are_genuinely_different_medicines(self):
        from app.services.medicine_matching_service import _variant_key
        for line in NEEDS_CHOICE:
            options = self.match(line)["options"]
            keys = {_variant_key(o) for o in options}
            self.assertEqual(len(keys), len(options), f"{line}: duplicate variants offered")

    def test_options_cover_the_common_strengths(self):
        strengths = {o["strength"] for o in self.match("Atorvastatin")["options"]}
        self.assertTrue({"10mg", "20mg", "40mg"} <= strengths, strengths)
        strengths = {o["strength"] for o in self.match("Paracetamol")["options"]}
        self.assertTrue({"500mg", "650mg"} <= strengths, strengths)

    def test_stating_the_strength_and_form_resolves_the_line(self):
        for line, strength, form in [("Tab Atorvastatin 40", "40mg", "Tablet"), ("Tab Amlodipine 5", "5mg", "Tablet"),
                                     ("Cap Amoxycillin 500", "500mg", "Capsule")]:
            r = self.match(line)
            self.assertEqual(r["status"], "matched", line)
            self.assertEqual((r["medicine"]["strength"], r["medicine"]["form"]), (strength, form), line)
            self.assertFalse(r.get("needs_disambiguation"), line)

    def test_a_strength_no_product_has_is_not_matched_or_guessed(self):
        # Nifedipine is sold as 5/10/20 mg here: "30" is unsupported, so no product is named at all
        for line in ("Nifedipine 30", "Nifedipine 30 ER", "Diclofenac 75 SR"):
            r = self.match(line)
            self.assertNotEqual(r["status"], "matched", line)
            if r["medicine"]:  # a closest guess, if any, must not contradict the stated strength
                self.assertIn("75" if "Diclofenac" in line else "30", r["medicine"]["strength"], line)

    # ---- regressions found by running realistic prescriptions end to end ------------------
    def test_dosing_schedule_does_not_silently_drop_a_medicine_line(self):
        # "1-0-1" added three numbers, so the line looked like a phone number and vanished
        for line, expect in [("Tab Dolo 650 1-0-1 x 5 days", "Dolo 650"), ("Tab Dolo 650 1 - 0 - 1", "Dolo 650"),
                             ("Tab Dolo 650 0-0-1/2", "Dolo 650"), ("Tab Augmentin 625 Duo 1-0-1", "Augmentin 625 Duo"),
                             ("Tab Metformin 500 SR 1-0-1", "SR")]:
            r = self.match(line)
            self.assertEqual(r["status"], "matched", line)
            self.assertIn(expect.lower(), r["medicine"]["medicine_name"].lower(), line)

    def test_a_schedule_is_not_read_as_a_strength(self):
        # the 1s and 0s of "1-0-1" must not corroborate (or contradict) a strength
        r = self.match("Tab Dolo 650 1-0-1")
        self.assertEqual(r["medicine"]["strength"], "650mg")

    def test_reference_numbers_are_still_not_medicines(self):
        from app.services.medicine_matching_service import _is_document_furniture
        self.assertFalse(_is_document_furniture("Tab Dolo 650 1-0-1 x 5 days"))
        for text in ("9 1 3 4 3 7 8", "Reg no 12345", "Mob 9 8 7 6 5", "Cardiology 1-0-1", "Phone 9-8-7-6"):
            self.assertTrue(_is_document_furniture(text) or self.match(text)["status"] == "skipped", text)

    def test_a_frequency_word_after_a_strength_does_not_hide_the_strength(self):
        # "650 SOS" / "650 BD": 650 is the strength and the next word is how often
        for line in ("Tab Paracetamol 650 SOS", "Tab Paracetamol 650 BD", "Tab Amlodipine 5 OD"):
            r = self.match(line)
            self.assertEqual(r["status"], "matched", line)
        self.assertEqual(self.match("Tab Paracetamol 650 SOS")["medicine"]["strength"], "650mg")

    def test_a_small_count_before_a_frequency_word_is_not_a_strength(self):
        # "Paracetamol 1 tds" says how many tablets, not which strength: still a choice
        r = self.match("Tab Paracetamol 1 tds")
        self.assertEqual(r["status"], "needs_verification")
        self.assertGreaterEqual(len(r["options"]), 2)

    def test_dosing_frequency_after_a_name_is_not_a_strength(self):
        r = self.match("Tab Paracetamol 650 1 tds")
        self.assertEqual(r["status"], "matched")
        self.assertEqual(r["medicine"]["strength"], "650mg")

    def test_is_generic_line(self):
        from app.services.medicine_matching_service import is_generic_line
        paracetamol = {"composition": "Paracetamol (650mg)", "primary_salt": "Paracetamol", "secondary_salt": None}
        for line in ("Paracetamol 650", "Tab Paracetamol 650mg BD", "Paracetamol 650 SR", "Syp Paracetamol"):
            self.assertTrue(is_generic_line(line, paracetamol), line)
        for line in ("Dolo 650", "Tab Crocin 650", "Calpol 650mg Tablet", "", "650"):
            self.assertFalse(is_generic_line(line, paracetamol), line)

    def test_non_medicines_are_not_matched(self):
        leaked = [t for t in MUST_NOT_MATCH if self.match(t)["status"] == "matched"]
        self.assertEqual(leaked, [])

    # ---- sustained release vs conventional ----------------------------------------------
    def test_sr_line_never_matches_a_conventional_product(self):
        for line in ("Tab Metformin 500 SR", "Glycomet SR 500"):
            r = self.match(line)
            self.assertEqual(r["status"], "matched", line)
            self.assertEqual(r["medicine"]["release_type"], "sr", line)
            for opt in r.get("options") or []:
                self.assertEqual(opt.get("release_type"), "sr", f"{line}: option {opt['medicine_name']}")

    def test_er_line_matches_extended_release(self):
        r = self.match("Metformin 500 ER")
        self.assertEqual(r["medicine"]["release_type"], "er")

    def test_unmatched_release_is_not_silently_substituted(self):
        # no 30 mg ER nifedipine tablet exists: the line must not be 'matched' to a 20 mg product
        r = self.match("Nifedipine 30 ER")
        self.assertNotEqual(r["status"], "matched")

    def test_conventional_line_prefers_conventional_product(self):
        r = self.match("Tab Metformin 500")
        self.assertIsNone(r["medicine"]["release_type"])

    # ---- combination medicines ------------------------------------------------------------
    def test_every_ingredient_and_strength_is_checked(self):
        from app.services.composition import ingredient_numerators
        # 500 + 500 does not exist: it must not be matched to a 1000/200 injection
        r = self.match("Amoxicillin 500 + Clavulanic acid 500")
        self.assertNotEqual(r["status"], "matched")
        for line, nums in [("Tab Amoxicillin 500 + Clavulanic acid 125", ["500", "125"]),
                           ("Telmisartan 40 + Hydrochlorothiazide 12.5", ["40", "12.5"]),
                           ("Tab Aceclofenac 100 + Paracetamol 325", ["100", "325"])]:
            r = self.match(line)
            self.assertEqual(r["status"], "matched", line)
            self.assertEqual(ingredient_numerators(r["medicine"]["composition"]), nums, line)

    def test_single_ingredient_line_does_not_pick_a_combination(self):
        r = self.match("Aceclofenac 100")
        self.assertEqual(r["status"], "matched")
        self.assertNotIn("+", r["medicine"]["composition"])
        r = self.match("Telma 40")
        self.assertNotIn("+", r["medicine"]["composition"])

    def test_combination_brand_resolves_to_its_combination(self):
        r = self.match("Zerodol P")
        self.assertIn("paracetamol", r["medicine"]["composition"].lower())
        self.assertIn("aceclofenac", r["medicine"]["composition"].lower())


class AlternativesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from app.db import get_connection
        cls.conn = get_connection()
        cls.cur = cls.conn.cursor(dictionary=True)

    @classmethod
    def tearDownClass(cls):
        cls.cur.close()
        cls.conn.close()
        cls.ctx.pop()

    def _alts(self, name):
        from app.models.price_model import find_alternatives
        self.cur.execute("SELECT * FROM Medicines WHERE medicine_name = %s LIMIT 1", (name,))
        m = self.cur.fetchone()
        self.assertIsNotNone(m, f"{name} missing from dataset")
        alts = find_alternatives(m["primary_salt"], m["secondary_salt"], m["strength"], m["form"], m["medicine_id"],
                                 release_type=m["release_type"], composition=m["composition"])
        ids = ",".join(str(a["medicine_id"]) for a in alts) or "0"
        self.cur.execute(f"SELECT medicine_id, release_type, composition, composition_incomplete FROM Medicines WHERE medicine_id IN ({ids})")
        return m, alts, self.cur.fetchall()

    def test_sr_alternatives_are_all_sr(self):
        m, alts, rows = self._alts("Allmet 500mg Tablet SR")
        self.assertEqual(m["release_type"], "sr")
        self.assertTrue(rows)
        self.assertEqual({r["release_type"] for r in rows}, {"sr"})

    def test_conventional_alternatives_exclude_modified_release(self):
        m, alts, rows = self._alts("Dolo 650 Tablet")
        self.assertTrue(rows)
        self.assertEqual({r["release_type"] for r in rows}, {None})

    def test_combination_alternatives_have_identical_composition(self):
        from app.services.composition import composition_key
        m, alts, rows = self._alts("Augmentin 625 Duo Tablet")
        self.assertTrue(rows)
        self.assertEqual({composition_key(r["composition"]) for r in rows}, {composition_key(m["composition"])})

    def test_truncated_products_are_never_offered_as_alternatives(self):
        for name in ("Augmentin 625 Duo Tablet", "Dolo 650 Tablet", "Zerodol-P Tablet"):
            _, _, rows = self._alts(name)
            self.assertFalse(any(r["composition_incomplete"] for r in rows), name)

    def test_no_alternatives_offered_for_a_product_with_incomplete_composition(self):
        from app.models.medicine_model import get_prescription_medicines
        from app.services.price_comparison_service import compare_prescription_medicine
        self.cur.execute("SELECT medicine_name FROM Medicines WHERE composition_incomplete = 1 AND price > 0 AND is_discontinued = 0 LIMIT 1")
        row = self.cur.fetchone()
        self.assertIsNotNone(row, "no flagged products - migration not run?")
        accounts = helpers.TempAccounts()
        try:
            pid = accounts.prescription(accounts.user())
            accounts.line(pid, row["medicine_name"])
            result = compare_prescription_medicine(get_prescription_medicines(pid)[0])
            self.assertEqual(result["alternatives"], [])
            self.assertIn("incomplete", result["note"])
        finally:
            accounts.cleanup()


if __name__ == "__main__":
    unittest.main()
