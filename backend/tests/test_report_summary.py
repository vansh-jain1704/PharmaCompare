"""
The report's plain-language summary: written by Gemini only when its answer passes strict checks, otherwise by PharmaCompare from the
same facts. Gemini is never called for real here: the HTTP call is mocked, so these tests prove what WOULD be sent and what would be accepted.
"""
import os
import tempfile
import unittest
from unittest import mock

from tests import helpers


def make_report(accounts, allergies=("Penicillin",), with_unidentified=True):
    """A prescription in several states, analysed by the real pipeline; returns (uid, pid)."""
    from app.routes.prescriptions import _rerun_analysis
    uid = accounts.user(allergies=list(allergies))
    pid = accounts.prescription(uid)
    accounts.line(pid, "Dolo 650 Tablet", raw_text="Tab Dolo 650", status="matched", confidence=1.0)
    accounts.line(pid, "Augmentin 625 Duo Tablet", raw_text="Tab Augmentin 625 Duo", status="matched", confidence=1.0)
    accounts.line(pid, "Omez FF 20 Tablet", raw_text="Cap Omez 20", status="matched", confidence=0.74)
    if with_unidentified:
        accounts.line(pid, None, raw_text="T Jane Q Patient's secret 100", status="needs_verification", confidence=0.5)
    _rerun_analysis(pid)
    return uid, pid


class Writers(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.accounts = helpers.TempAccounts()
        from app.models.prescription_model import get_prescription_by_id
        from app.services import report_summary_service
        from app.services.smart_report_service import collect_report_data
        self.svc = report_summary_service
        self.uid, self.pid = make_report(self.accounts)
        self.data = collect_report_data(self.pid, get_prescription_by_id(self.pid))
        self.facts = self.svc.build_facts(self.data)

    def tearDown(self):
        self.accounts.cleanup()
        self.ctx.pop()

    # ---- what the facts hold, and what they never hold ----------------------------------------------------------------
    def test_the_facts_are_counts_and_medicine_details(self):
        f = self.facts
        self.assertEqual((f["lines"], f["not_identified"], f["to_check"]), (4, 1, 1))          # Omez: capsule line matched to a tablet
        self.assertEqual({m["name"] for m in f["identified"]}, {"Dolo 650 Tablet", "Augmentin 625 Duo Tablet", "Omez FF 20 Tablet"})
        self.assertEqual(f["allergy_alerts"], 1)
        self.assertFalse(f["has_pharmacy_reports"])

    def test_nothing_that_identifies_the_patient_is_in_the_facts(self):
        text = self.svc.facts_text(self.facts)
        self.assertNotIn("Penicillin", text)                      # the allergen is never sent, only that an alert exists
        self.assertNotIn("Jane", text)                            # unidentified lines contribute a count, never their text
        self.assertNotIn("secret", text)
        self.assertNotIn("Unit Test", text)                       # the account name
        self.assertNotIn("example.invalid", text)
        self.assertIn("Lines with an allergy alert: 1.", text)
        self.assertIn("Lines not identified: 1.", text)

    # ---- the local writer -----------------------------------------------------------------------------------------------
    def test_the_local_summary_states_everything_flagged_and_that_prices_are_reference_prices(self):
        text = self.svc.deterministic_summary(self.facts)
        for needle in ("4 lines were read", "3 medicines are identified", "Dolo 650 Tablet", "1 line needs your check", "1 line is not identified",
                       "1 line carries an allergy alert", "reference prices from a dataset snapshot, not live pharmacy prices"):
            self.assertIn(needle, text)
        self.assertNotRegex(text, self.svc.FORBIDDEN)
        self.assertNotIn("Penicillin", text)

    def test_the_local_summary_passes_its_own_validation_in_every_state(self):
        base = dict(self.facts)
        for change in ({}, {"allergy_alerts": 0}, {"to_check": 0, "not_identified": 0}, {"findings": 0, "finding_severities": {}},
                       {"identified": [], "lines": 0, "to_check": 0, "not_identified": 0, "allergy_alerts": 0, "findings": 0, "finding_severities": {}},
                       {"saving": 0, "saving_counted_on": 0}, {"saving": 93.5, "saving_counted_on": 2, "original_total": 166.65}):
            facts = {**base, **change}
            ok, why = self.svc.validate(self.svc.deterministic_summary(facts), facts)
            self.assertTrue(ok, f"{change}: {why}")

    def test_the_wording_is_right_for_one_and_for_many(self):
        one = self.svc.deterministic_summary({**self.facts, "lines": 1, "identified": [self.facts["identified"][0]], "to_check": 0, "not_identified": 0, "allergy_alerts": 0})
        self.assertIn("1 line was read", one)
        self.assertIn("1 medicine is identified", one)

    # ---- the guard on a generated summary ---------------------------------------------------------------------------------
    def good(self):
        return ("4 lines were read and 3 medicines are identified. 1 line needs your check and 1 line is not identified. "
                "1 line has an allergy alert, and the safety check recorded findings: see the safety section. "
                "Prices are reference prices from a dataset snapshot, not live pharmacy prices.")

    def test_a_faithful_summary_is_accepted(self):
        facts = {**self.facts, "findings": 2, "finding_severities": {"Moderate": 2}}
        self.assertEqual(self.svc.validate(self.good(), facts), (True, None))

    def test_words_of_advice_assurance_or_diagnosis_are_rejected(self):
        for phrase in ("This combination is safe.", "Dolo is taken 3 times a day.", "Take it at night.", "You should stop taking Dolo.", "Consider switching to a cheaper brand and switch to it.", "This will cure the fever.",
                       "The diagnosis is an infection.", "There is no interaction.", "Start taking it at night.", "It is unsafe.", "You must take it daily."):
            ok, why = self.svc.validate(self.good() + " " + phrase, self.facts)
            self.assertFalse(ok, phrase)
            self.assertIn("forbidden", why)

    def test_an_invented_number_is_rejected(self):
        for extra in ("Dolo comes in a pack of 15.", "The course is 14 days.", "It comes in a strip of 77."):
            ok, why = self.svc.validate(self.good() + " " + extra, self.facts)
            self.assertFalse(ok, extra)
            self.assertIn("numbers that are not in the facts", why)

    def test_a_strength_or_count_cannot_be_passed_off_as_a_price(self):
        # 500 and 625 ARE in the facts (as Augmentin's strengths), so the number check alone would let them through
        self.assertIn("500", self.svc.facts_text(self.facts))
        for extra in ("You could save Rs 500.", "It costs 120 rupees.", "A saving of ₹625 is possible.", "That is Rs. 4 less."):
            ok, why = self.svc.validate(self.good() + " " + extra, self.facts)
            self.assertFalse(ok, extra)
            self.assertTrue("rupee amount" in why or "numbers that are not in the facts" in why, (extra, why))
        facts = {**self.facts, "saving": 93.5, "saving_counted_on": 2, "original_total": 166.65}
        for fine in ("Rs 93.50", "Rs. 93.5", "₹166.65", "166.65 rupees"):
            self.assertEqual(self.svc.validate(self.good() + f" The counted amount is {fine}.", facts), (True, None), fine)

    def test_numbers_that_are_in_the_facts_are_allowed(self):
        facts = {**self.facts, "saving": 93.5, "saving_counted_on": 2, "original_total": 166.65}
        text = self.good() + " The counted saving is Rs 93.50 of Rs 166.65 across 2 medicines."
        self.assertEqual(self.svc.validate(text, facts), (True, None))

    def test_leaving_out_a_flag_is_rejected(self):
        facts = {**self.facts, "findings": 2, "finding_severities": {"Major": 2}}
        for text, reason in (
            ("4 lines were read. 1 line is not identified. 1 line has an allergy alert. Findings were recorded. Prices are reference prices.", "lines that need checking"),
            ("4 lines were read. 1 line needs your check. 1 line has an allergy alert. Findings were recorded. Prices are reference prices.", "not identified"),
            ("4 lines were read. 1 line needs your check. 1 line is not identified. Findings were recorded. Prices are reference prices.", "allergy"),
            ("4 lines were read. 1 line needs your check. 1 line is not identified. 1 line has an allergy alert. Prices are reference prices.", "safety findings"),
            ("4 lines were read. 1 line needs your check. 1 line is not identified. 1 line has an allergy alert. Findings were recorded.", "reference prices"),
        ):
            ok, why = self.svc.validate(text, facts)
            self.assertFalse(ok, text)
            self.assertIn(reason, why)

    def test_empty_or_long_text_is_rejected(self):
        self.assertEqual(self.svc.validate("", self.facts)[0], False)
        self.assertEqual(self.svc.validate("   ", self.facts)[0], False)
        ok, why = self.svc.validate(self.good() + " word" * 300, self.facts)
        self.assertEqual((ok, why), (False, "too long"))

    # ---- choosing the writer ----------------------------------------------------------------------------------------------------
    def test_without_a_key_the_local_writer_is_used_and_says_so(self):
        with mock.patch("app.config.Config.GEMINI_API_KEY", ""), mock.patch("app.services.report_summary_service.requests.post") as post:
            out = self.svc.summarise(self.data)
        post.assert_not_called()                                              # nothing leaves the server without a key
        self.assertEqual((out["source"], out["label"], out["rejected"]), ("local", self.svc.LABEL_LOCAL, None))

    def reply(self, text, status=200):
        response = mock.Mock(status_code=status, text="boom")
        response.json.return_value = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
        return response

    def test_a_valid_gemini_answer_is_used_and_labelled_as_gemini(self):
        facts = self.svc.build_facts(self.data)
        text = self.good() if facts["findings"] else self.good().replace(" and the safety check recorded findings: see the safety section", "")
        with mock.patch("app.config.Config.GEMINI_API_KEY", "test-key-not-real"), mock.patch("app.services.report_summary_service.requests.post", return_value=self.reply(text)):
            out = self.svc.summarise(self.data)
        if self.svc.validate(text, facts)[0]:
            self.assertEqual((out["source"], out["label"]), ("gemini", self.svc.LABEL_GEMINI))
            self.assertEqual(out["text"], text)
        else:
            self.assertEqual(out["source"], "local")

    def test_an_invalid_gemini_answer_is_thrown_away_for_the_local_summary(self):
        bad = "This combination is safe and you should take 7 tablets."
        with mock.patch("app.config.Config.GEMINI_API_KEY", "test-key-not-real"), mock.patch("app.services.report_summary_service.requests.post", return_value=self.reply(bad)):
            out = self.svc.summarise(self.data)
        self.assertEqual(out["source"], "local")
        self.assertIn("forbidden", out["rejected"])
        self.assertNotRegex(out["text"], self.svc.FORBIDDEN)
        self.assertNotIn("7 tablets", out["text"])

    def test_a_failing_gemini_call_falls_back_without_raising_and_without_the_key_in_the_logs(self):
        import requests
        secret = "AIzaSyFAKE_not_a_real_key_0123456789abcdef"
        err = requests.ConnectionError(f"HTTPSConnectionPool: url: /v1beta/models/x:generateContent?key={secret}")
        with mock.patch("app.config.Config.GEMINI_API_KEY", secret), mock.patch("app.services.report_summary_service.requests.post", side_effect=err):
            with self.assertLogs("app.services.report_summary_service", level="ERROR") as logged:
                out = self.svc.summarise(self.data)
        self.assertEqual(out["source"], "local")
        self.assertEqual(out["rejected"], "the Gemini request failed")
        self.assertNotIn(secret, "\n".join(logged.output))

    def test_a_non_200_answer_falls_back(self):
        with mock.patch("app.config.Config.GEMINI_API_KEY", "test-key-not-real"), mock.patch("app.services.report_summary_service.requests.post", return_value=self.reply("x", status=500)):
            self.assertEqual(self.svc.summarise(self.data)["source"], "local")

    def test_what_would_be_sent_to_gemini_holds_no_patient_details(self):
        sent = {}

        def capture(url, params=None, json=None, timeout=None):
            sent["url"], sent["params"], sent["json"] = url, params, json
            return self.reply("x")
        with mock.patch("app.config.Config.GEMINI_API_KEY", "test-key-not-real"), mock.patch("app.services.report_summary_service.requests.post", side_effect=capture):
            self.svc.summarise(self.data)
        payload = str(sent["json"])
        for private in ("Penicillin", "Jane", "secret", "Unit Test", "example.invalid", "unittest_dummy"):
            self.assertNotIn(private, payload, private)
        self.assertIn("Dolo 650 Tablet", payload)
        self.assertIn("Lines not identified: 1.", payload)
        self.assertIn("Do not give medical advice", payload)                 # the rules travel with every request
        self.assertEqual(sent["json"]["generationConfig"]["temperature"], 0.2)


class ThroughTheApiAndPdf(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.client = self.app.test_client()
        self.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        with self.app.app_context():
            self.uid, self.pid = make_report(self.accounts)
            self.other = self.accounts.user(allergies=[])
            self.h = {"Authorization": f"Bearer {create_access_token(identity=str(self.uid))}"}
            self.h_other = {"Authorization": f"Bearer {create_access_token(identity=str(self.other))}"}

    def tearDown(self):
        with self.app.app_context():
            self.accounts.cleanup()

    def test_the_summary_is_private_and_says_who_wrote_it(self):
        self.assertEqual(self.client.get(f"/api/prescriptions/{self.pid}/summary").status_code, 401)
        self.assertEqual(self.client.get(f"/api/prescriptions/{self.pid}/summary", headers=self.h_other).status_code, 404)
        with mock.patch("app.config.Config.GEMINI_API_KEY", ""):
            body = self.client.get(f"/api/prescriptions/{self.pid}/summary", headers=self.h).get_json()
        self.assertEqual((body["source"], body["label"]), ("local", "Written by PharmaCompare from the figures in this report."))
        self.assertIn("3 medicines are identified", body["text"])

    def test_the_pdf_carries_the_summary_and_its_label(self):
        import pypdfium2 as pdfium
        from app.models.prescription_model import get_prescription_by_id
        from app.services.smart_report_service import build_report_pdf
        path = os.path.join(tempfile.mkdtemp(), "r.pdf")
        with self.app.app_context(), mock.patch("app.config.Config.GEMINI_API_KEY", ""):
            build_report_pdf(self.pid, get_prescription_by_id(self.pid), path)
        pdf = pdfium.PdfDocument(path)
        try:
            text = " ".join(" ".join(pdf[i].get_textpage().get_text_range().split()) for i in range(len(pdf)))
        finally:
            pdf.close()
        self.assertIn("Summary", text)
        self.assertIn("3 medicines are identified", text)
        self.assertIn("Written by PharmaCompare from the figures in this report.", text)
        self.assertLess(text.index("Summary"), text.index("Doctor prescribed medicines"))


if __name__ == "__main__":
    unittest.main()
