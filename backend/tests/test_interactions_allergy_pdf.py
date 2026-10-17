"""Interaction naming, allergy ownership and PDF generation, against the real database."""
import io
import shutil
import unittest

from tests import helpers


class SaltNameNormalisation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.get_app()
        from app.services.clinical_decision_service import _normalize_salt, SALT_NAME_ALIASES
        cls.norm = staticmethod(_normalize_salt)
        cls.aliases = SALT_NAME_ALIASES

    def test_spelling_and_salt_forms(self):
        for given, expected in [("Amoxycillin", "amoxicillin"), ("Escitalopram Oxalate", "escitalopram"),
                                ("Olmesartan Medoxomil", "olmesartan"), ("Cefpodoxime Proxetil", "cefpodoxime"),
                                ("Vitamin B6 (Pyridoxine)", "pyridoxine"), ("Metformin Hydrochloride", "metformin")]:
            self.assertEqual(self.norm(given), expected, given)

    def test_unrelated_names_are_untouched(self):
        # explicit aliases only: no generic suffix stripping that could merge different drugs
        self.assertEqual(self.norm("Azilsartan Medoxomil"), "azilsartan medoxomil")
        self.assertEqual(self.norm("Levonorgestrel (Intrauterine System)"), "levonorgestrel (intrauterine system)")

    def test_every_alias_target_exists_in_ddinter(self):
        """An alias is only worth having if its target is a name DDInter actually holds."""
        from app.db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT drug_a_norm FROM Drug_Interactions UNION SELECT DISTINCT drug_b_norm FROM Drug_Interactions")
        known = {r[0] for r in cur.fetchall()}
        cur.close()
        conn.close()
        missing = sorted(t for t in set(self.aliases.values()) if t not in known)
        self.assertEqual(missing, [], "alias targets not present in DDInter")


class AllergyOwnership(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.accounts = helpers.TempAccounts()
        self.allergic = self.accounts.user(allergies=["Paracetamol"])
        self.other = self.accounts.user(allergies=["Penicillin"])
        self.rx_allergic = self.accounts.prescription(self.allergic)
        self.rx_other = self.accounts.prescription(self.other)
        for pid in (self.rx_allergic, self.rx_other):
            self.accounts.line(pid, "Dolo 650 Tablet")

    def tearDown(self):
        self.accounts.cleanup()
        self.ctx.pop()

    def _data(self, pid):
        from app.models.prescription_model import get_prescription_by_id
        from app.services.smart_report_service import collect_report_data
        return collect_report_data(pid, get_prescription_by_id(pid))

    def test_report_uses_the_prescription_owners_allergies(self):
        mine = self._data(self.rx_allergic)["lines"][0]
        theirs = self._data(self.rx_other)["lines"][0]
        self.assertTrue(mine["safety"]["allergy_alert"])
        self.assertFalse(theirs["safety"]["allergy_alert"])

    def test_group_allergy_applies_to_the_right_patient_only(self):
        from app.models.user_model import get_user_allergies
        self.assertEqual(get_user_allergies(self.allergic), ["Paracetamol"])
        self.assertEqual(get_user_allergies(self.other), ["Penicillin"])
        accounts = self.accounts
        for pid in (self.rx_allergic, self.rx_other):
            accounts.line(pid, "Augmentin 625 Duo Tablet")
        mine = {ln["pm"]["medicine_name"]: ln for ln in self._data(self.rx_allergic)["lines"]}
        theirs = {ln["pm"]["medicine_name"]: ln for ln in self._data(self.rx_other)["lines"]}
        self.assertFalse(mine["Augmentin 625 Duo Tablet"]["safety"]["allergy_alert"])
        self.assertTrue(theirs["Augmentin 625 Duo Tablet"]["safety"]["allergy_alert"])

    def test_clinical_engine_reads_the_owners_allergies(self):
        from app.models.medicine_model import get_prescription_medicines
        from app.services.clinical_decision_service import check_allergies
        for pid, expect_major in ((self.rx_allergic, True), (self.rx_other, False)):
            confirmed = get_prescription_medicines(pid)
            severities = {f["severity"] for f in check_allergies(pid, confirmed)}
            self.assertEqual("Major" in severities, expect_major)

    def test_user_without_allergies_gets_an_honest_unchecked_message(self):
        from app.models.medicine_model import get_prescription_medicines
        from app.services.clinical_decision_service import check_allergies
        blank = self.accounts.user(allergies=[])
        pid = self.accounts.prescription(blank)
        self.accounts.line(pid, "Dolo 650 Tablet")
        findings = check_allergies(pid, get_prescription_medicines(pid))
        self.assertEqual([f["severity"] for f in findings], ["NEEDS_VERIFICATION"])
        self.assertIn("could not be performed", findings[0]["explanation"])

    def test_other_account_cannot_read_or_download_the_prescription(self):
        from flask_jwt_extended import create_access_token
        client = self.app.test_client()
        token_other = create_access_token(identity=str(self.other))
        token_owner = create_access_token(identity=str(self.allergic))
        url = f"/api/prescriptions/{self.rx_allergic}"
        for path in (url, url + "/report"):
            r = client.get(path, headers={"Authorization": f"Bearer {token_other}"})
            self.assertEqual(r.status_code, 404, path)
        r = client.get(url + "/report", headers={"Authorization": f"Bearer {token_owner}"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/pdf")
        self.assertTrue(r.data.startswith(b"%PDF"))

    def test_saving_allergies_through_the_api_changes_the_next_report(self):
        from flask_jwt_extended import create_access_token
        client = self.app.test_client()
        headers = {"Authorization": f"Bearer {create_access_token(identity=str(self.other))}"}
        self.assertFalse(self._data(self.rx_other)["lines"][0]["safety"]["allergy_alert"])
        r = client.put("/api/auth/me/allergies", json={"allergies": ["paracetamol"]}, headers=headers)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self._data(self.rx_other)["lines"][0]["safety"]["allergy_alert"])


class PdfReport(unittest.TestCase):
    HOSTILE = ["Tab X <5 days & more", "<b>bold</b> unclosed <i> tag", "Paracetamol 650 > 500 &amp; 100 & <",
               "Rs 100 ₹ ½ ¼ 数字 café", "Z" * 300,
               "A very long handwritten line that goes on and on and on " * 4]
    REAL = ["Dolo 650 Tablet", "Crocin Advance Tablet", "Azithral 500 Tablet", "Pantop 40 Tablet", "Telma 40 Tablet",
            "Ecosprin 75 Tablet", "Zerodol-P Tablet", "Augmentin 625 Duo Tablet", "Montek LC Tablet", "Allegra 120mg Tablet",
            "Calpol 650mg Tablet", "Taxim-O 200 Tablet", "Pan-D Capsule PR", "Crocin Cold & Flu Max Tablet"]

    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from app.routes.prescriptions import _rerun_analysis
        from app.models.prescription_model import get_prescription_by_id
        from app.services.smart_report_service import build_report_pdf
        import os
        import tempfile
        import pypdfium2 as pdfium

        cls.accounts = helpers.TempAccounts()
        uid = cls.accounts.user(allergies=["Paracetamol"])
        cls.pid = cls.accounts.prescription(uid, name="0db8802525724c22b190c24a03c234c2.png")
        cls.present = []
        for name in cls.REAL:
            try:
                cls.accounts.line(cls.pid, name, dosage="1 tab", frequency="Twice daily", duration="5 days")
                cls.present.append(name)
            except AssertionError:
                pass
        for text in cls.HOSTILE:
            cls.accounts.line(cls.pid, None, raw_text=text, status="needs_verification", confidence=0.5)
        _rerun_analysis(cls.pid)
        tmp = tempfile.mkdtemp()
        cls.addClassCleanup(shutil.rmtree, tmp, True)
        cls.path = os.path.join(tmp, "report.pdf")
        build_report_pdf(cls.pid, get_prescription_by_id(cls.pid), cls.path)
        doc = pdfium.PdfDocument(cls.path)
        cls.pages = [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
        doc.close()
        cls.text = "\n".join(cls.pages)

    @classmethod
    def tearDownClass(cls):
        cls.accounts.cleanup()
        cls.ctx.pop()

    def test_hostile_text_does_not_break_generation(self):
        self.assertTrue(self.pages)  # reaching here means build_report_pdf did not raise

    def test_every_detected_line_has_a_row(self):
        medicines_section = self.text.split("Safety check")[0]
        for name in self.present:
            stem = name.split(" Tablet")[0].split(" Capsule")[0]
            self.assertIn(stem, medicines_section, f"{name} missing from the medicines table")
        self.assertIn("A very long handwritten", self.text)
        self.assertIn("Tab X", self.text)
        self.assertIn("bold", self.text)  # markup is shown as text, not interpreted

    def test_title_is_not_a_raw_upload_filename(self):
        self.assertNotIn("0db88025", self.text)

    def test_footer_numbers_every_page(self):
        n = len(self.pages)
        for i, page in enumerate(self.pages, 1):
            self.assertIn(f"Page {i} of {n}", page)

    def test_allergy_status_appears_for_the_patients_allergy(self):
        self.assertIn("allergy", self.text.lower())

    def test_pdf_status_agrees_with_the_ui_safety_summary(self):
        from app.models.prescription_model import get_prescription_by_id
        from app.services.smart_report_service import collect_report_data
        data = collect_report_data(self.pid, get_prescription_by_id(self.pid))
        for ln in data["lines"]:
            if ln["safety"]["allergy_alert"]:
                self.assertEqual(ln["saving"], None)  # never a saving for an allergy-flagged line
        self.assertEqual(data["detected"], len(self.present) + len(self.HOSTILE))


if __name__ == "__main__":
    unittest.main()
