"""
Two small backend behaviours:
  1. when no medicine on a prescription is confirmed, the safety finding says that the interaction, duplicate
     and allergy checks have not run (it used to blame the account's empty allergy list);
  2. each upload logs which OCR engine read it, how many lines it found and whether the cloud engine failed and
     EasyOCR took over - counts and names only, never prescription text, account details or keys.
The OCR engines are faked here: no network call, no billing, nothing sent anywhere.
"""
import io
import unittest
from unittest import mock

from PIL import Image

from tests import helpers

SECRET_LINE = "SECRETPATIENTLINE Tab Zzzyx 999"


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, "PNG")
    buf.seek(0)
    return buf


class NoConfirmedMedicineWording(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.accounts = helpers.TempAccounts()

    def tearDown(self):
        self.accounts.cleanup()
        self.ctx.pop()

    def analyse(self, allergies, lines):
        from app.services.clinical_decision_service import run_clinical_decision_engine
        uid = self.accounts.user(allergies=allergies)
        pid = self.accounts.prescription(uid)
        pms = [self.accounts.line(pid, name, raw_text=raw, status=status, confidence=0.5 if status != "matched" else 0.9) for name, raw, status in lines]
        return pid, pms, run_clinical_decision_engine(pid)

    def test_nothing_confirmed_says_that_no_check_ran(self):
        for allergies in ([], ["Penicillin"]):
            _, _, result = self.analyse(allergies, [(None, "T Lincont 100", "needs_verification"), (None, "Tap D - risl 60 k", "needs_verification")])
            self.assertEqual(len(result["findings"]), 1, allergies)
            f = result["findings"][0]
            self.assertIn("No medicine on this prescription has been confirmed yet", f["explanation"])
            self.assertIn("interaction, duplicate and allergy checks have not run", f["explanation"])
            self.assertNotIn("could not be performed", f["explanation"])           # the old, misleading cause
            self.assertNotIn("No allergies are declared", f["explanation"])
            self.assertEqual((f["issue_type"], f["severity"]), ("allergy_check", "NEEDS_VERIFICATION"))   # API contract unchanged
            self.assertIsNone(f["confidence"])
            self.assertEqual(f["medicines_involved"], [])

    def test_an_empty_prescription_gets_the_same_honest_message(self):
        _, _, result = self.analyse([], [])
        self.assertEqual(len(result["findings"]), 1)
        self.assertIn("have not run", result["findings"][0]["explanation"])

    def test_the_finding_is_stored_and_fits_its_column(self):
        from app.models.safety_model import get_findings
        pid, _, result = self.analyse([], [(None, "T Lincont 100", "needs_verification")])
        stored = get_findings(pid)
        self.assertEqual(len(stored), 1)
        self.assertIn("have not run", stored[0]["explanation"])
        self.assertLessEqual(len(stored[0]["data_source"]), 150)
        self.assertIn("no medicine", stored[0]["data_source"])
        self.assertNotIn("allergies declared", stored[0]["data_source"])

    def test_no_check_result_is_invented_for_an_unconfirmed_line(self):
        _, _, result = self.analyse(["Penicillin"], [(None, "Cap Augmentin 625", "needs_verification")])
        self.assertEqual({f["issue_type"] for f in result["findings"]}, {"allergy_check"})
        self.assertFalse(any(f["severity"] == "Major" for f in result["findings"]))
        self.assertIn("Analyzed 0 confirmed medicine(s)", result["summary"])

    def test_once_a_medicine_is_confirmed_the_normal_wording_returns(self):
        # unchanged behaviour with at least one confirmed medicine
        _, _, result = self.analyse([], [("Dolo 650 Tablet", "Tab Dolo 650", "matched")])
        self.assertIn("could not be performed", result["findings"][0]["explanation"])
        self.assertNotIn("have not run", result["findings"][0]["explanation"])
        _, _, result = self.analyse(["Penicillin"], [("Dolo 650 Tablet", "Tab Dolo 650", "matched")])
        self.assertIn("You declared: Penicillin", result["findings"][0]["explanation"])
        _, _, result = self.analyse(["Penicillin"], [("Augmentin 625 Duo Tablet", "Tab Augmentin 625 Duo", "matched")])
        self.assertTrue(any(f["severity"] == "Major" and f["issue_type"] == "allergy_check" for f in result["findings"]))

    def test_confirming_a_line_by_hand_replaces_the_message_on_the_next_analysis(self):
        from app.db import get_connection
        from app.models.medicine_model import update_prescription_medicine_match
        from app.models.safety_model import get_findings
        from app.routes.prescriptions import _rerun_analysis
        pid, pms, _ = self.analyse([], [(None, "Tab Dolo 650", "needs_verification")])
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT medicine_id FROM Medicines WHERE medicine_name = 'Dolo 650 Tablet' LIMIT 1")
        medicine_id = cur.fetchone()[0]
        cur.close()
        conn.close()
        update_prescription_medicine_match(pms[0], medicine_id)
        _rerun_analysis(pid)
        texts = " ".join(f["explanation"] for f in get_findings(pid))
        self.assertNotIn("have not run", texts)
        self.assertIn("could not be performed", texts)   # now an ordinary analysis of one confirmed medicine


class OcrProviderLogging(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.accounts = helpers.TempAccounts()
        with self.app.app_context():
            self.uid = self.accounts.user(allergies=[])
        from flask_jwt_extended import create_access_token
        with self.app.app_context():
            self.headers = {"Authorization": f"Bearer {create_access_token(identity=str(self.uid))}"}
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            self.accounts.cleanup()

    def upload(self, fake_result):
        with mock.patch("app.routes.prescriptions.extract_text", return_value=fake_result), \
             mock.patch("app.config.Config.GOOGLE_VISION_API_KEY", "FAKEKEY-do-not-log-12345"), \
             self.assertLogs(self.app.logger, level="INFO") as captured:
            response = self.client.post("/api/prescriptions/upload", headers=self.headers,
                                        data={"file": (_png(), "rx.png")}, content_type="multipart/form-data")
        return response, [r for r in captured.records if "OCR for prescription" in r.getMessage()], captured

    def result(self, provider, lines=2, readable=True, **extra):
        rows = [{"text": SECRET_LINE if i == 0 else f"line {i}", "confidence": 0.9, "uncertain": False} for i in range(lines)]
        return {"text": "\n".join(r["text"] for r in rows), "lines": rows, "confidence": 0.9 if readable else 0.1, "readable": readable, "provider": provider, **extra}

    def test_cloud_without_fallback_is_logged(self):
        response, records, _ = self.upload(self.result("cloud", lines=2))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(records), 1)
        self.assertRegex(records[0].getMessage(), r"provider=cloud lines=2 fallback=False readable=True$")
        self.assertEqual(records[0].levelname, "INFO")

    def test_a_fallback_to_easyocr_is_logged_as_such(self):
        response, records, _ = self.upload(self.result("easyocr", lines=3, fallback=True))
        self.assertEqual(response.status_code, 201)
        self.assertRegex(records[0].getMessage(), r"provider=easyocr lines=3 fallback=True readable=True$")

    def test_easyocr_chosen_directly_is_not_a_fallback(self):
        _, records, _ = self.upload(self.result("easyocr", lines=1))
        self.assertIn("provider=easyocr lines=1 fallback=False", records[0].getMessage())

    def test_an_unreadable_upload_is_logged_too(self):
        response, records, _ = self.upload(self.result("cloud", lines=1, readable=False))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(records), 1)
        self.assertIn("readable=False", records[0].getMessage())

    def test_the_log_never_contains_prescription_text_account_details_or_keys(self):
        _, records, captured = self.upload(self.result("cloud", lines=2))
        everything = "\n".join(r.getMessage() for r in captured.records)
        for forbidden in (SECRET_LINE, "SECRETPATIENT", "Zzzyx", "FAKEKEY", "do-not-log", "example.invalid", "Unit Test", "Bearer", "eyJ"):
            self.assertNotIn(forbidden, everything, forbidden)
        # the OCR line itself carries only: id, provider, count, two booleans
        self.assertRegex(records[0].getMessage(), r"^OCR for prescription \d+: provider=\w+ lines=\d+ fallback=(True|False) readable=(True|False)$")


class OcrFallbackFlag(unittest.TestCase):
    """extract_text marks a result that came from the fallback, and only that one."""

    @classmethod
    def setUpClass(cls):
        helpers.get_app()
        from app.services import ocr_service
        cls.ocr = ocr_service

    def test_cloud_failure_falls_back_and_says_so(self):
        easy = {"text": "", "lines": [], "confidence": 0.0, "readable": False, "provider": "easyocr"}
        with mock.patch("app.config.Config.OCR_PROVIDER", "auto"), mock.patch.object(self.ocr.cloud_ocr_service, "is_configured", return_value=True), \
             mock.patch.object(self.ocr.cloud_ocr_service, "extract_words", side_effect=RuntimeError("boom")), \
             mock.patch.object(self.ocr, "extract_text_easyocr", return_value=dict(easy)), self.assertLogs(self.ocr.logger, level="ERROR"):
            result = self.ocr.extract_text("x.png", "png")
        self.assertEqual((result["provider"], result.get("fallback")), ("easyocr", True))

    def test_cloud_success_and_direct_easyocr_are_not_fallbacks(self):
        with mock.patch("app.config.Config.OCR_PROVIDER", "auto"), mock.patch.object(self.ocr.cloud_ocr_service, "is_configured", return_value=True), \
             mock.patch.object(self.ocr.cloud_ocr_service, "extract_words", return_value=[]):
            self.assertFalse(self.ocr.extract_text("x.png", "png").get("fallback"))
        easy = {"text": "", "lines": [], "confidence": 0.0, "readable": False, "provider": "easyocr"}
        with mock.patch("app.config.Config.OCR_PROVIDER", "easyocr"), mock.patch.object(self.ocr, "extract_text_easyocr", return_value=dict(easy)):
            self.assertFalse(self.ocr.extract_text("x.png", "png").get("fallback"))

    def test_a_pinned_cloud_provider_still_refuses_to_fall_back(self):
        with mock.patch("app.config.Config.OCR_PROVIDER", "cloud"), mock.patch.object(self.ocr.cloud_ocr_service, "extract_words", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.ocr.extract_text("x.png", "png")


if __name__ == "__main__":
    unittest.main()
