"""
Alternatives and recommendations (Objective 3), verified instead of assumed.

A property test over a fixed random sample of real products from the catalogue checks that EVERY alternative the engine offers is the same
medicine (ingredients and strengths, form, release type), live, priced and complete; that savings are only claimed against the same pack
quantity with an unflagged price; that the arithmetic is right; and that recommendations stay within their limits. Then the notes that say what
a comparison does and does not establish are checked on the screen's payload and in the PDF.
"""
import os
import random
import tempfile
import unittest

from tests import helpers

SAMPLE = 150
SEED = 7


class AlternativesAreTheSameMedicine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from app.db import get_connection
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""SELECT medicine_id FROM Medicines WHERE is_discontinued = 0 AND price > 0 AND composition_incomplete = 0
                       AND MOD(medicine_id, 7) = 3""")
        ids = [r["medicine_id"] for r in cur.fetchall()]
        chosen = random.Random(SEED).sample(ids, SAMPLE)
        cur.execute(f"SELECT * FROM Medicines WHERE medicine_id IN ({', '.join(['%s'] * len(chosen))})", chosen)
        cls.sample = cur.fetchall()
        cur.close()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def pm_row(self, m):
        return {**m, "pm_id": 0, "raw_text": m["medicine_name"], "match_status": "user_confirmed", "match_confidence": None}

    def entries(self):
        from app.services.price_comparison_service import compare_prescription_medicine
        for m in self.sample:
            yield m, compare_prescription_medicine(self.pm_row(m))

    def test_every_alternative_has_the_same_ingredients_strengths_form_and_release_type(self):
        from app.models.medicine_model import get_medicine_by_id
        from app.services.composition import composition_key
        checked = with_alternatives = 0
        for m, entry in self.entries():
            for alt in entry["alternatives"]:
                full = get_medicine_by_id(alt["medicine_id"])
                label = f"{m['medicine_name']} -> {full['medicine_name']}"
                self.assertEqual(composition_key(full["composition"]), composition_key(m["composition"]), label)
                self.assertEqual((full["primary_salt"], full["secondary_salt"]), (m["primary_salt"], m["secondary_salt"]), label)
                self.assertEqual((full["strength"], full["form"], full["release_type"]), (m["strength"], m["form"], m["release_type"]), label)
                self.assertFalse(full["is_discontinued"], label)
                self.assertFalse(full["composition_incomplete"], label)
                self.assertGreater(float(full["price"]), 0, label)
                self.assertNotEqual(full["medicine_id"], m["medicine_id"], label)
                checked += 1
            with_alternatives += bool(entry["alternatives"])
        self.assertGreater(checked, 300)                     # the sample really exercised the rule
        self.assertGreater(with_alternatives, SAMPLE * 0.8)

    def test_a_saving_is_only_claimed_against_the_same_pack_quantity_with_an_unflagged_price(self):
        claimed = 0
        for m, entry in self.entries():
            ref = entry["reference_price"]["price"]
            for alt in entry["alternatives"]:
                label = f"{m['medicine_name']} -> {alt['medicine_name']}"
                if alt["counts_for_savings"]:
                    claimed += 1
                    self.assertTrue(alt["same_pack_quantity"], label)
                    self.assertLess(alt["price"], ref, label)
                    self.assertIsNone(alt["price_flag"], label)
                    self.assertFalse(alt["is_discontinued"], label)
                    self.assertIsNone(entry["reference_price"]["price_flag"], label)
                if not alt["same_pack_quantity"] or alt["price_flag"]:
                    self.assertIsNone(alt["savings_percent"], label)          # a percentage over different amounts of medicine is withheld
                    self.assertFalse(alt["counts_for_savings"], label)
        self.assertGreater(claimed, 100)

    def test_the_savings_arithmetic_is_right(self):
        checked = 0
        for m, entry in self.entries():
            ref = entry["reference_price"]["price"]
            for alt in entry["alternatives"]:
                self.assertAlmostEqual(alt["price_difference"], round(alt["price"] - ref, 2), places=2)
                if alt["savings_percent"] is not None:
                    self.assertAlmostEqual(alt["savings_percent"], round((ref - alt["price"]) / ref * 100, 2), places=2)
                    checked += 1
        self.assertGreater(checked, 100)

    def test_alternatives_with_the_same_pack_quantity_are_listed_first_then_cheapest_first(self):
        for m, entry in self.entries():
            alts = entry["alternatives"]
            same = [a["same_pack_quantity"] for a in alts]
            self.assertEqual(same, sorted(same, reverse=True), m["medicine_name"])
            for flag in (True, False):
                prices = [a["price"] for a in alts if a["same_pack_quantity"] == flag]
                self.assertEqual(prices, sorted(prices), m["medicine_name"])
            self.assertLessEqual(len(alts), 10)

    def test_recommendations_stay_within_their_limits(self):
        from app.services.generic_recommendation_service import DOCTOR_ADVICE, MAX_RECOMMENDATIONS_PER_MEDICINE, build_recommendations_for_medicine
        total = 0
        for m, entry in self.entries():
            recs = build_recommendations_for_medicine(entry)
            self.assertLessEqual(len(recs), MAX_RECOMMENDATIONS_PER_MEDICINE)
            self.assertEqual(len({r["recommended_medicine_id"] for r in recs}), len(recs))
            for r in recs:
                total += 1
                self.assertLess(r["price_difference"], 0, m["medicine_name"])               # strictly cheaper
                self.assertIn(r["confidence_score"], (0.7, 1.0))
                self.assertIn(DOCTOR_ADVICE, r["reason"])
                self.assertIn("Same active ingredient", r["reason"])
                self.assertIn(m["strength"], r["reason"])
                self.assertNotIn("recommend switching", r["reason"].lower())
        self.assertGreater(total, 100)

    def test_a_medicine_with_an_incomplete_ingredient_list_is_offered_no_alternatives(self):
        from app.db import get_connection
        from app.services.price_comparison_service import compare_prescription_medicine
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM Medicines WHERE composition_incomplete = 1 AND price > 0 LIMIT 5")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        self.assertTrue(rows)
        for m in rows:
            entry = compare_prescription_medicine(self.pm_row(m))
            self.assertEqual(entry["alternatives"], [], m["medicine_name"])
            self.assertIn("incomplete", entry["note"])

    def test_a_line_that_is_not_settled_is_never_compared(self):
        from app.services.price_comparison_service import compare_prescription_medicine
        row = {**self.pm_row(self.sample[0]), "match_status": "needs_verification", "medicine_id": None}
        entry = compare_prescription_medicine(row)
        self.assertEqual((entry["verification_status"], entry["alternatives"], entry["reference_price"]), ("needs_verification", [], None))


class PackOrdering(unittest.TestCase):
    """The database orders by a text pattern; the list must be ordered by the same rule the savings use (quantity AND kind)."""

    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def test_a_count_of_one_is_not_ranked_as_one_millilitre(self):
        from app.db import get_connection
        from app.models.price_model import find_alternatives
        from app.services import price_quality
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM Medicines WHERE medicine_name = 'Betabolin 25 Injection' LIMIT 1")
        m = cur.fetchone()
        cur.close()
        conn.close()
        self.assertEqual(m["pack_size"], "vial of 1 ml Injection")
        rows = find_alternatives(m["primary_salt"], m["secondary_salt"], m["strength"], m["form"], m["medicine_id"], release_type=m["release_type"],
                                 composition=m["composition"], pack_quantity=price_quality.pack_quantity(m["pack_size"]), pack_size=m["pack_size"])
        flags = [price_quality.same_pack_quantity(m["pack_size"], r["pack_size"]) for r in rows]
        self.assertEqual(flags, sorted(flags, reverse=True))                   # every genuinely comparable pack before any other
        prices = [float(r["price"]) for r, f in zip(rows, flags) if f]
        self.assertEqual(prices, sorted(prices))
        self.assertLessEqual(len(rows), 10)

    def test_without_the_pack_text_the_old_behaviour_is_unchanged(self):
        from app.models.price_model import find_alternatives
        rows = find_alternatives("Paracetamol", None, "650mg", "Tablet", -1, pack_quantity=15)
        self.assertLessEqual(len(rows), 10)
        self.assertTrue(rows)


class NotesOnWhatIsAndIsNotCompared(unittest.TestCase):
    def test_the_notes_state_what_was_matched_what_was_not_and_that_safety_checks_carry_over(self):
        from app.services.recommendation_notes import notes_for
        n = notes_for()
        self.assertIn("the same active ingredients, each at the same strength", n["matched"])
        self.assertTrue(any("dosage form" in x for x in n["matched"]))
        self.assertTrue(any("release type" in x for x in n["matched"]))
        self.assertTrue(any("inactive ingredients" in x for x in n["not_compared"]))
        self.assertTrue(any("quality" in x and "absorbed" in x for x in n["not_compared"]))
        self.assertIn("interaction and allergy checks apply to these products unchanged", n["safety"])
        self.assertIn("ask your doctor or pharmacist first", n["ask_first"])
        self.assertIsNone(n["information_only"])

    def test_an_unsettled_line_marks_its_alternatives_as_information_only(self):
        from app.services.recommendation_notes import notes_for
        for flag in ("needs_check", "ocr_uncertain", "needs_disambiguation", "confirmed_with_conflicts"):
            n = notes_for(**{flag: True})
            self.assertIn("for information only", n["information_only"], flag)
            self.assertIn("no saving is counted", n["information_only"], flag)

    def test_no_note_recommends_switching_or_claims_equivalence(self):
        from app.services import recommendation_notes
        text = " ".join(recommendation_notes.MATCHED + recommendation_notes.NOT_COMPARED) + recommendation_notes.SAFETY_CARRIES_OVER + recommendation_notes.ASK_FIRST
        for banned in ("equivalent", "bioequivalent to", "you should switch", "safe to substitute", "interchangeable"):
            self.assertNotIn(banned, text.lower())


class OnTheScreensPayloadAndInThePdf(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.client = self.app.test_client()
        self.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        from app.routes.prescriptions import _rerun_analysis
        with self.app.app_context():
            self.uid = self.accounts.user(allergies=[])
            self.pid = self.accounts.prescription(self.uid)
            self.h = {"Authorization": f"Bearer {create_access_token(identity=str(self.uid))}"}
            self.clean = self.accounts.line(self.pid, "Dolo 650 Tablet", raw_text="Tab Dolo 650", status="matched", confidence=1.0)
            self.flagged = self.accounts.line(self.pid, "Omez FF 20 Tablet", raw_text="Cap Omez 20", status="matched", confidence=0.74)
            self.unsettled = self.accounts.line(self.pid, None, raw_text="T Lincont 100", status="needs_verification", confidence=0.8)
            _rerun_analysis(self.pid)

    def tearDown(self):
        with self.app.app_context():
            self.accounts.cleanup()

    def lines(self):
        return {d["pm_id"]: d for d in self.client.get(f"/api/prescriptions/{self.pid}", headers=self.h).get_json()["detected_medicines"]}

    def test_identified_lines_carry_the_notes_and_unidentified_ones_do_not(self):
        lines = self.lines()
        self.assertIn("same strength", lines[self.clean]["alternatives_notes"]["matched"][0])
        self.assertIsNone(lines[self.clean]["alternatives_notes"]["information_only"])
        self.assertIsNone(lines[self.unsettled]["alternatives_notes"])

    def test_a_line_that_needs_a_check_marks_its_alternatives_information_only(self):
        self.assertIn("for information only", self.lines()[self.flagged]["alternatives_notes"]["information_only"])

    def test_the_pdf_states_how_alternatives_are_chosen_and_what_is_not_compared(self):
        import pypdfium2 as pdfium
        from app.models.prescription_model import get_prescription_by_id
        from app.services.smart_report_service import build_report_pdf
        path = os.path.join(tempfile.mkdtemp(), "r.pdf")
        with self.app.app_context():
            build_report_pdf(self.pid, get_prescription_by_id(self.pid), path)
        pdf = pdfium.PdfDocument(path)
        try:
            text = " ".join(" ".join(pdf[i].get_textpage().get_text_range().split()) for i in range(len(pdf)))
        finally:
            pdf.close()
        for needle in ("How alternatives are chosen:", "the same active ingredients, each at the same strength", "Not compared:", "inactive ingredients",
                       "interaction and allergy checks apply to these products unchanged", "ask your doctor or pharmacist first"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
