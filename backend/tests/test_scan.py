"""
Scanning a medicine pack: ranked CANDIDATES only (never a confirmation), nothing stored, the photo gone afterwards, errors that never echo a key.
OCR is mocked, so no image is sent anywhere; the matcher and the catalogue are the real ones.
"""
import glob
import io
import os
import tempfile
import unittest
from unittest import mock

from tests import helpers


def lines(*texts):
    return [{"text": t, "confidence": 0.95, "uncertain": False} for t in texts]


def scan_dirs():
    return set(glob.glob(os.path.join(tempfile.gettempdir(), "pharmacompare_scan_*")))


class Candidates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from app.services import scan_service
        cls.svc = scan_service

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def fake(self, table):
        calls = []

        def matcher(text):
            calls.append(text)
            return table.get(text, {"status": "skipped", "medicine": None, "confidence": None})
        matcher.calls = calls
        return matcher

    def test_a_product_the_reader_settled_on_comes_first_then_by_score(self):
        m = self.fake({
            "A": {"status": "needs_verification", "medicine": {"medicine_id": 1}, "confidence": 0.9, "guesses": [{"medicine_id": 1, "score": 0.9, "reasons": ["r1"]}, {"medicine_id": 2, "score": 0.6}]},
            "B": {"status": "matched", "medicine": {"medicine_id": 3}, "confidence": 0.7},
        })
        got = self.svc.candidates_from_lines(lines("A", "B"), matcher=m)
        self.assertEqual([c["medicine_id"] for c in got], [3, 1, 2])
        self.assertEqual([c["settled_by_reader"] for c in got], [True, False, False])
        self.assertEqual(got[1]["reasons"], ["r1"])

    def test_one_product_found_on_several_lines_appears_once_with_its_best_reading(self):
        m = self.fake({
            "A": {"status": "needs_verification", "medicine": {"medicine_id": 1}, "confidence": 0.5, "guesses": [{"medicine_id": 1, "score": 0.5}]},
            "B": {"status": "matched", "medicine": {"medicine_id": 1}, "confidence": 0.99},
        })
        got = self.svc.candidates_from_lines(lines("A", "B"), matcher=m)
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0]["score"], got[0]["settled_by_reader"], got[0]["from_line"]), (0.99, True, "B"))

    def test_lines_the_matcher_skips_offer_nothing_and_do_not_use_up_the_budget(self):
        table = {f"L{i}": {"status": "matched", "medicine": {"medicine_id": i}, "confidence": 0.5 + i / 100} for i in range(1, 30)}
        m = self.fake(table)
        skipped = [f"junk{i}" for i in range(20)]
        got = self.svc.candidates_from_lines(lines(*skipped, *[f"L{i}" for i in range(1, 30)]), matcher=m)
        self.assertEqual(len([c for c in m.calls if c.startswith("L")]), self.svc.MAX_LINES)      # a bounded number of real lookups
        self.assertLessEqual(len(got), self.svc.MAX_CANDIDATES)

    def test_packaging_lines_never_reach_the_matcher(self):
        m = self.fake({})
        self.svc.candidates_from_lines(lines("Store below 30 C", "Micro Labs Limited", "B.No. 1234 Exp 08/2027", "MRP Rs 34.27", "Keep out of reach of children", "Rx only"), matcher=m)
        self.assertEqual(m.calls, [])

    def test_the_real_matcher_finds_a_pack_by_its_brand_and_its_composition_line(self):
        got = self.svc.candidates_from_lines(lines("DOLO 650", "Paracetamol Tablets IP 650 mg", "Micro Labs Limited", "MRP Rs 34.27 per strip of 15 tablets", "Store below 30 C"))
        self.assertEqual(got[0]["medicine_id"], 58235)                         # Dolo 650 Tablet
        self.assertTrue(got[0]["settled_by_reader"])
        self.assertEqual(got[0]["from_line"], "DOLO 650")
        self.assertGreaterEqual(len(got), 2)                                   # the composition line adds same-ingredient products

    def test_text_that_resembles_nothing_gives_no_candidates(self):
        self.assertEqual(self.svc.candidates_from_lines(lines("xqzvbw", "kkkjjj")), [])


class ThroughTheRoute(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.client = self.app.test_client()
        self.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        with self.app.app_context():
            self.uid = self.accounts.user(allergies=[])
            self.h = {"Authorization": f"Bearer {create_access_token(identity=str(self.uid))}"}

    def tearDown(self):
        with self.app.app_context():
            self.accounts.cleanup()

    def post(self, name="pack.png", data=b"fake image bytes", headers=True):
        return self.client.post("/api/medicines/scan", headers=self.h if headers else {}, data={"file": (io.BytesIO(data), name)}, content_type="multipart/form-data")

    def ocr(self, *texts, readable=True):
        return {"text": "\n".join(texts), "lines": lines(*texts), "confidence": 0.95 if readable else 0.1, "readable": readable, "provider": "test"}

    def counts(self):
        from app.db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        out = []
        for table in ("Prescriptions", "Prescription_Medicines", "OCR_Results", "System_Logs", "Pharmacy_Offers"):
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            out.append(cur.fetchone()[0])
        cur.close()
        conn.close()
        return out

    def test_it_needs_a_login_and_a_supported_image(self):
        self.assertEqual(self.post(headers=False).status_code, 401)
        self.assertEqual(self.client.post("/api/medicines/scan", headers=self.h).status_code, 400)
        r = self.post(name="notes.txt")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["allowed_types"], ["jpeg", "jpg", "png"])
        self.assertEqual(self.post(name="doc.pdf").status_code, 400)

    def test_a_scan_returns_candidates_never_a_confirmation(self):
        with mock.patch("app.routes.scan.extract_text", return_value=self.ocr("DOLO 650", "Paracetamol Tablets IP 650 mg", "Micro Labs Limited")):
            r = self.post()
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertIs(body["confirmed"], False)
        self.assertIn("not a confirmation", body["notice"])
        self.assertIn("cannot tell whether a pack is genuine", body["notice"])
        first = body["candidates"][0]
        self.assertEqual((first["medicine_name"], first["settled_by_reader"], first["from_line"]), ("Dolo 650 Tablet", True, "DOLO 650"))
        for key in ("medicine_id", "composition", "form", "strength", "display_strength", "manufacturer", "pack_size", "price", "is_discontinued", "release_label", "score", "reasons"):
            self.assertIn(key, first, key)
        self.assertEqual(body["lines"][0]["text"], "DOLO 650")

    def test_a_combination_pack_shows_every_ingredients_strength(self):
        with mock.patch("app.routes.scan.extract_text", return_value=self.ocr("Pan-D")):
            body = self.post().get_json()
        names = {c["medicine_name"]: c for c in body["candidates"]}
        self.assertEqual(names["Pan-D Capsule PR"]["display_strength"], "Domperidone 30mg + Pantoprazole 40mg")

    def test_nothing_is_stored_and_the_photo_is_deleted(self):
        before_counts, before_dirs = self.counts(), scan_dirs()
        with mock.patch("app.routes.scan.extract_text", return_value=self.ocr("DOLO 650")):
            self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.counts(), before_counts)                         # no prescription, no line, no log, no offer
        self.assertEqual(scan_dirs(), before_dirs)                             # the temporary folder with the photo is gone

    def test_the_photo_is_deleted_even_when_the_ocr_fails(self):
        before = scan_dirs()
        with mock.patch("app.routes.scan.extract_text", side_effect=RuntimeError("boom")):
            self.assertEqual(self.post().status_code, 500)
        self.assertEqual(scan_dirs(), before)

    def test_an_ocr_failure_never_echoes_a_key(self):
        secret = "AIzaSyFAKE_not_a_real_key_0123456789abcdef"
        with mock.patch("app.config.Config.GOOGLE_VISION_API_KEY", secret), \
             mock.patch("app.routes.scan.extract_text", side_effect=RuntimeError(f"could not reach Vision: /v1/images:annotate?key={secret}")):
            with self.assertLogs(level="ERROR") as logged:
                r = self.post()
        self.assertEqual(r.status_code, 500)
        self.assertNotIn(secret, r.get_data(as_text=True))
        self.assertNotIn(secret, "\n".join(logged.output))

    def test_a_photo_too_unclear_to_read_says_so_with_the_photo_notes(self):
        with mock.patch("app.routes.scan.extract_text", return_value=self.ocr("x", readable=False)):
            r = self.post()
        self.assertEqual(r.status_code, 422)
        body = r.get_json()
        self.assertEqual((body["confirmed"], body["candidates"]), (False, []))
        self.assertIn("too unclear", body["message"])

    def test_text_that_matches_nothing_says_so_instead_of_guessing(self):
        with mock.patch("app.routes.scan.extract_text", return_value=self.ocr("xqzvbw", "kkkjjj")):
            body = self.post().get_json()
        self.assertEqual(body["candidates"], [])
        self.assertIn("Nothing on file matches", body["message"])


if __name__ == "__main__":
    unittest.main()
