"""
Regressions from a REAL handwritten prescription (cloud OCR read it at 0.74 average confidence).

The lines below are the OCR's own output for the medicine and instruction lines (the
doctor/hospital lines are left out on purpose). Several of the medicines written on it
(Shelcal, D-Rise 60K, Linogen XT, ...) are not in the dataset at all, so the right outcome
for them is "needs verification", never a confident match to a similar-looking product.
"""
import unittest

from tests import helpers

# written medicines the dataset cannot identify from this handwriting
UNIDENTIFIABLE = ["T Lincont 100", "T shel cal soong 0-1-0", "Tap D - risl 60 k", "T. Linogen . XT", "T. pan - D 100", "T. Shelcal 500"]
# durations, headings and instructions: not medicines
NOT_MEDICINES = ["Once in a week f Sweets", "MEDICAL ADVISE :", "x30dys", "X - 7 dys", "X 30d", "730", "#xillary temperature monitoring"]


class HandwrittenPrescription(unittest.TestCase):
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

    def test_nothing_the_dataset_cannot_identify_is_matched(self):
        for line in UNIDENTIFIABLE:
            r = self.match(line)
            self.assertEqual(r["status"], "needs_verification", f"{line!r} -> {r['status']} {(r['medicine'] or {}).get('medicine_name')}")

    def test_a_guess_never_contradicts_the_number_written_on_the_line(self):
        # "Lincont 100" must not be guessed as a 600 mg product, "Shelcal 500" not as a 400 mg one
        for line in ("T Lincont 100", "T. Shelcal 500", "T. pan - D 100"):
            result = self.match(line)
            guess = result["medicine"]
            if guess and not result.get("ignored_schedule_digits"):
                self.assertIn("100" if "100" in line else "500", f"{guess['strength']} {guess['medicine_name']}", line)
            # the ONE exception: three digits that look like a dose schedule ("100" = "1-0-0") may be set aside to offer the product
            # the name fits - never to settle the line, and always saying so
            if result.get("ignored_schedule_digits"):
                self.assertEqual(result["status"], "needs_verification", line)
                self.assertIn("dose schedule", result["guesses"][0]["reasons"][0], line)

    def test_durations_headings_and_instructions_are_not_medicines(self):
        for line in NOT_MEDICINES:
            self.assertEqual(self.match(line)["status"], "skipped", line)

    def test_an_instruction_is_never_matched_to_a_product(self):
        # "Once in a week x 8 weeks" was read "...f Sweets" and matched "Odan Syrup Sweet Orange"
        for line in ("Once in a week x 8 weeks", "Once a day after food", "Twice daily for 5 days", "After food", "Continue for 7 days"):
            self.assertEqual(self.match(line)["status"], "skipped", line)

    def test_a_bare_T_means_tablet_and_never_a_syrup(self):
        from app.services.medicine_matching_service import _inferred_form
        for line in ("T. Dolo 650", "T Lincont 100", "1. T. Pan-D", "  t. telma 40"):
            self.assertEqual(_inferred_form(line), "tablet", line)
        for line in ("Vitamin T", "Telma T 40", "Ascoril", "Dolo 650"):
            self.assertIsNone(_inferred_form(line), line)
        for line in ("T Lincont 100", "T. Lincont 100"):
            r = self.match(line)
            self.assertNotIn("syrup", ((r["medicine"] or {}).get("form") or "").lower(), line)

    def test_leading_T_still_matches_real_tablets(self):
        for line, expect in (("T. Dolo 650", "Dolo 650"), ("T Telma 40", "Telma 40"), ("T. Pantop 40", "Pantop 40")):
            r = self.match(line)
            self.assertEqual(r["status"], "matched", line)
            self.assertIn(expect, r["medicine"]["medicine_name"], line)

    def test_a_strength_alone_cannot_identify_a_product(self):
        # "Shelcal 500" became "Shellgel Softgel Capsule" because 500 was its calcium carbonate strength
        r = self.match("Shelcal 500")
        self.assertNotEqual(r["status"], "matched")
        for line in ("Shelcal 500", "T. Shelcal 500", "Shelcal 500 tablet"):
            guess = self.match(line)["medicine"]
            self.assertFalse(guess and "Shellgel" in guess["medicine_name"], line)

    def test_an_unlabelled_number_only_confirms_the_first_ingredient_or_the_name(self):
        from app.db import get_connection
        from app.services.medicine_matching_service import _combination_strength_agreement
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM Medicines WHERE medicine_name = 'Shellgel Softgel Capsule' LIMIT 1")
        shellgel = cur.fetchone()          # Calcitriol (0.25mcg) + Calcium Carbonate (500mg)
        cur.execute("SELECT * FROM Medicines WHERE medicine_name = 'Augmentin 625 Duo Tablet' LIMIT 1")
        augmentin = cur.fetchone()         # 625 is in the name, not an ingredient strength
        cur.close()
        conn.close()
        self.assertIsNone(_combination_strength_agreement("Shelcal 500", shellgel))
        self.assertEqual(_combination_strength_agreement("Augmentin 625", augmentin), 1.0)
        self.assertEqual(_combination_strength_agreement("Shellgel 0.25", shellgel), 1.0)

    def test_the_whole_prescription_end_to_end(self):
        """The OCR lines of the real prescription, through the real detection and analysis pipeline."""
        from app.routes.prescriptions import _rerun_analysis, _run_medicine_detection
        accounts = helpers.TempAccounts()
        try:
            pid = accounts.prescription(accounts.user(allergies=[]))
            lines = ["MEDICAL ADVISE :", "2TTE 2016 OTG", "T Lincont 100", "x30dys", "T shel cal soong 0-1-0", "730",
                     "Tap D - risl 60 k", "Once in a week f Sweets", "T. Linogen . XT", "X 30d", "T. pan - D 100", "X - 7 dys",
                     "#xillary temperature monitoring"]
            detected = _run_medicine_detection(pid, [{"text": t} for t in lines])
            _rerun_analysis(pid)
            raw = [d["raw_text"] for d in detected]
            self.assertEqual(raw, ["2TTE 2016 OTG", "T Lincont 100", "T shel cal soong 0-1-0", "Tap D - risl 60 k", "T. Linogen . XT", "T. pan - D 100"])
            self.assertTrue(all(d["status"] == "needs_verification" for d in detected))
            self.assertTrue(all(d["medicine"] is None or d["medicine"]["form"] != "Syrup" for d in detected))
        finally:
            accounts.cleanup()


if __name__ == "__main__":
    unittest.main()
