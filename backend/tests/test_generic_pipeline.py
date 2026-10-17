"""
Generic-name handling end to end: detection -> safety summary -> API -> PDF -> the
person's own choice. Uses the real database; every account/prescription is removed.
"""
import os
import shutil
import tempfile
import unittest

from tests import helpers


class GenericLinePipeline(unittest.TestCase):
    LINES = ["Metformin", "Tab Paracetamol 650", "Dolo 650", "Tab Metformin 500 SR", "Nifedipine 30"]

    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from flask_jwt_extended import create_access_token
        from app.routes.prescriptions import _run_medicine_detection, _rerun_analysis

        cls.accounts = helpers.TempAccounts()
        cls.uid = cls.accounts.user(allergies=[])
        cls.pid = cls.accounts.prescription(cls.uid)
        _run_medicine_detection(cls.pid, [{"text": t} for t in cls.LINES])
        _rerun_analysis(cls.pid)
        cls.headers = {"Authorization": f"Bearer {create_access_token(identity=str(cls.uid))}"}
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.accounts.cleanup()
        cls.ctx.pop()

    def rows(self):
        r = self.client.get(f"/api/prescriptions/{self.pid}", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        return {m["raw_text"]: m for m in r.get_json()["detected_medicines"]}

    def test_under_specified_line_is_unidentified_with_candidates(self):
        row = self.rows()["Metformin"]
        self.assertEqual(row["match_status"], "needs_verification")
        self.assertIsNone(row["medicine_id"])
        self.assertTrue(row["needs_disambiguation"])
        self.assertGreaterEqual(len(row["match_options"]), 2)
        self.assertIn("strength", row["verification_reason"])
        self.assertIn("several different products", row["verification_label"])
        self.assertEqual(row["verification_status"], "pending_verification")

    def test_unsupported_strength_is_unidentified_without_candidates(self):
        row = self.rows()["Nifedipine 30"]
        self.assertEqual(row["match_status"], "needs_verification")
        self.assertIsNone(row["medicine_id"])
        self.assertFalse(row["needs_disambiguation"])

    def test_generic_line_is_flagged_brand_unspecified(self):
        rows = self.rows()
        self.assertTrue(rows["Tab Paracetamol 650"]["brand_unspecified"])
        self.assertFalse(rows["Dolo 650"]["brand_unspecified"])
        self.assertEqual(rows["Tab Paracetamol 650"]["match_status"], "matched")

    def test_release_type_is_reported_by_the_api(self):
        rows = self.rows()
        self.assertEqual(rows["Tab Metformin 500 SR"]["release_type"], "sr")
        self.assertEqual(rows["Tab Metformin 500 SR"]["release_label"], "sustained release")
        self.assertIsNone(rows["Dolo 650"]["release_type"])
        self.assertIsNone(rows["Dolo 650"]["release_label"])

    def test_no_saving_is_claimed_against_a_representative_brand(self):
        from app.models.prescription_model import get_prescription_by_id
        from app.services.smart_report_service import collect_report_data
        data = collect_report_data(self.pid, get_prescription_by_id(self.pid))
        by_raw = {ln["pm"]["raw_text"]: ln for ln in data["lines"]}
        generic = by_raw["Tab Paracetamol 650"]
        self.assertIsNone(generic["saving"])
        self.assertIsNone(generic["price"])
        self.assertEqual(generic["reason"], "No brand named on the prescription")
        self.assertEqual(by_raw["Metformin"]["status"], "Needs verification")
        self.assertRegex(by_raw["Metformin"]["confidence"], r"^\d+ possible products$")

    def test_pdf_says_the_same_things_as_the_api(self):
        import pypdfium2 as pdfium
        from app.models.prescription_model import get_prescription_by_id
        from app.services.smart_report_service import build_report_pdf
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "g.pdf")
        build_report_pdf(self.pid, get_prescription_by_id(self.pid), path)
        doc = pdfium.PdfDocument(path)
        # the PDF wraps lines inside table cells, so compare on normalised whitespace
        text = " ".join(" ".join(doc[i].get_textpage().get_text_range() for i in range(len(doc))).split())
        doc.close()
        self.assertIn("possible products", text)
        self.assertIn("does not say which strength", text)
        self.assertIn("Generic name written", text)
        self.assertIn("Contains: Paracetamol", text)
        self.assertIn("sustained release", text.lower())
        self.assertIn("No brand named on the prescription", text)


class PersonChoosesCandidate(unittest.TestCase):
    """Own prescription per test: confirming a line changes it."""

    def setUp(self):
        self.app = helpers.get_app()
        self.ctx = self.app.app_context()
        self.ctx.push()
        from flask_jwt_extended import create_access_token
        from app.routes.prescriptions import _run_medicine_detection, _rerun_analysis
        self.accounts = helpers.TempAccounts()
        uid = self.accounts.user(allergies=[])
        self.pid = self.accounts.prescription(uid)
        _run_medicine_detection(self.pid, [{"text": "Metformin"}])
        _rerun_analysis(self.pid)
        self.headers = {"Authorization": f"Bearer {create_access_token(identity=str(uid))}"}
        self.client = self.app.test_client()

    def tearDown(self):
        self.accounts.cleanup()
        self.ctx.pop()

    def row(self):
        r = self.client.get(f"/api/prescriptions/{self.pid}", headers=self.headers)
        return r.get_json()["detected_medicines"][0]

    def test_choosing_a_candidate_makes_it_the_persons_confirmed_product(self):
        before = self.row()
        option = before["match_options"][0]
        r = self.client.patch(f"/api/prescriptions/{self.pid}/medicines/{before['pm_id']}",
                              json={"medicine_id": option["medicine_id"]}, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        after = self.row()
        self.assertEqual(after["match_status"], "user_confirmed")
        self.assertEqual(after["medicine_id"], option["medicine_id"])
        self.assertFalse(after["brand_unspecified"])  # the person named this product on purpose
        self.assertEqual(after["verification_status"], "verified_by_user")
        self.assertIsNone(after["verification_reason"])


if __name__ == "__main__":
    unittest.main()
