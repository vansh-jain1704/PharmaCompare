"""
OCR: clean and degraded prescriptions, and what happens to a shaky reading.

The images are rendered here and read by the LOCAL engine (EasyOCR), so the tests are
repeatable and make no network or billing calls. (The Google Vision path was exercised
by hand on the same kinds of image; see the Phase 1 follow-up report.) Real
handwriting is NOT covered: there are no genuine handwritten samples in the project and
a rendered "handwriting" font is only a rough stand-in.
"""
import os
import shutil
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from tests import helpers

FONTS = r"C:\Windows\Fonts"
LINES = ["1. Tab Dolo 650 1-0-1 x 5 days", "2. Tab Pantop 40 1-0-0 before food", "3. Tab Telma 40 OD",
         "4. Tab Metformin 500 SR 1-0-1", "5. Cap Omeprazole 20 BD"]
INGREDIENTS = ("paracetamol", "pantoprazole", "telmisartan", "metformin", "omeprazole")


def render(font_file="arial.ttf", size=40):
    img = Image.new("RGB", (1200, 120 + 90 * len(LINES)), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(os.path.join(FONTS, font_file), size)
    for i, line in enumerate(LINES):
        draw.text((40, 40 + 90 * i), line, font=font, fill=(20, 20, 20))
    return img


def noisy(img, amount):
    arr = np.array(img).astype(np.int16) + np.random.RandomState(1).randint(-amount, amount, (img.size[1], img.size[0], 3))
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def variants():
    base = render()
    return {
        "clean": base,
        "rotated": base.rotate(6, expand=True, fillcolor="white"),
        "low_contrast_noise": noisy(ImageEnhance.Contrast(base).enhance(0.15), 30),
        "low_resolution": base.resize((base.size[0] // 3, base.size[1] // 3)).resize(base.size),
        "script_font": render("segoesc.ttf", 40),
        "heavy_noise": noisy(base, 110),
    }


class LocalOcr(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from app.services.ocr_service import extract_text_easyocr
        from app.services.medicine_matching_service import match_line
        cls.dir = tempfile.mkdtemp()
        cls.addClassCleanup(shutil.rmtree, cls.dir, True)
        cls.results = {}
        for name, img in variants().items():
            path = os.path.join(cls.dir, name + ".png")
            img.save(path)
            result = extract_text_easyocr(path, "png")
            cls.results[name] = [(ln, match_line(ln["text"].strip())) for ln in result["lines"] if ln["text"].strip()]
        blur_path = os.path.join(cls.dir, "blur.png")
        render().filter(ImageFilter.GaussianBlur(5)).save(blur_path)
        cls.blurred = extract_text_easyocr(blur_path, "png")

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def test_clean_printed_prescription_finds_every_medicine(self):
        matched = [m for _, m in self.results["clean"] if m["status"] == "matched"]
        self.assertEqual(len(matched), len(LINES))
        for medicine, ingredient in zip((m["medicine"] for m in matched), INGREDIENTS):
            self.assertIn(ingredient, medicine["composition"].lower())

    def test_a_degraded_image_never_produces_a_wrong_medicine(self):
        """Whatever the damage, a line is either matched to one of the real medicines or left for the person."""
        for name, rows in self.results.items():
            for line, match in rows:
                if match["status"] != "matched":
                    continue
                composition = match["medicine"]["composition"].lower()
                self.assertTrue(any(i in composition for i in INGREDIENTS),
                                f"{name}: {line['text']!r} matched {match['medicine']['medicine_name']} ({composition})")

    def test_an_unreadable_image_is_rejected_not_guessed(self):
        self.assertFalse(self.blurred["readable"])
        self.assertLess(self.blurred["confidence"], 0.35)
        for line in self.blurred["lines"]:
            from app.services.medicine_matching_service import match_line
            self.assertNotEqual(match_line(line["text"].strip())["status"], "matched", line["text"])

    def test_misread_names_are_left_for_the_person(self):
        # the script-font image misreads "Metformin 500" as "S00": that line must not be matched
        misread = [m for ln, m in self.results["script_font"] if "etformin" in ln["text"] and "500" not in ln["text"]]
        for m in misread:
            self.assertNotEqual(m["status"], "matched")

    def test_uncertain_lines_are_marked_by_the_ocr(self):
        flagged = [ln for rows in self.results.values() for ln, _ in rows if ln["uncertain"]]
        self.assertTrue(flagged, "no image produced an uncertain line: the degradations are too mild to test anything")


class UncertainReadingsAreNeverSettled(unittest.TestCase):
    """A medicine matched from text the OCR was unsure about must be flagged, on screen data and in the PDF."""

    def setUp(self):
        self.app = helpers.get_app()
        self.ctx = self.app.app_context()
        self.ctx.push()
        from app.models.prescription_model import save_ocr_result
        self.accounts = helpers.TempAccounts()
        self.uid = self.accounts.user(allergies=[])
        self.pid = self.accounts.prescription(self.uid)
        self.shaky = self.accounts.line(self.pid, "Dolo 650 Tablet", raw_text="1. Tab Dolo 650 1-0-1 x 5 days")
        self.sure = self.accounts.line(self.pid, "Telma 40 Tablet", raw_text="3. Tab Telma 40 OD")
        save_ocr_result(self.pid, "x", 0.8, lines=[
            {"text": "1. Tab Dolo 650 1-0-1 x 5 days", "confidence": 0.49, "uncertain": True},
            {"text": "3. Tab Telma 40 OD", "confidence": 0.99, "uncertain": False},
        ])
        from app.routes.prescriptions import _rerun_analysis
        _rerun_analysis(self.pid)

    def tearDown(self):
        self.accounts.cleanup()
        self.ctx.pop()

    def data(self):
        from app.models.prescription_model import get_prescription_by_id
        from app.services.smart_report_service import collect_report_data
        return {ln["pm"]["pm_id"]: ln for ln in collect_report_data(self.pid, get_prescription_by_id(self.pid))["lines"]}

    def test_only_the_uncertain_line_is_flagged(self):
        lines = self.data()
        self.assertTrue(lines[self.shaky]["safety"]["ocr_uncertain"])
        self.assertAlmostEqual(lines[self.shaky]["safety"]["ocr_confidence"], 0.49)
        self.assertEqual(lines[self.shaky]["safety"]["verification_status"], "flagged_for_review")
        self.assertIn("low confidence", lines[self.shaky]["safety"]["verification_label"])
        self.assertFalse(lines[self.sure]["safety"]["ocr_uncertain"])

    def test_the_flagged_line_is_check_match_and_earns_no_saving(self):
        lines = self.data()
        self.assertEqual(lines[self.shaky]["status"], "Check match")
        self.assertIsNone(lines[self.shaky]["saving"])
        self.assertEqual(lines[self.shaky]["reason"], "Not counted: check match first")
        self.assertEqual(lines[self.sure]["status"], "Matched")

    def test_the_api_carries_the_flag(self):
        from flask_jwt_extended import create_access_token
        headers = {"Authorization": f"Bearer {create_access_token(identity=str(self.uid))}"}
        rows = {r["pm_id"]: r for r in self.app.test_client().get(f"/api/prescriptions/{self.pid}", headers=headers).get_json()["detected_medicines"]}
        self.assertTrue(rows[self.shaky]["ocr_uncertain"])
        self.assertFalse(rows[self.sure]["ocr_uncertain"])

    def test_the_pdf_shows_the_same_status(self):
        import pypdfium2 as pdfium
        from app.models.prescription_model import get_prescription_by_id
        from app.services.smart_report_service import build_report_pdf
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "o.pdf")
        build_report_pdf(self.pid, get_prescription_by_id(self.pid), path)
        doc = pdfium.PdfDocument(path)
        text = " ".join(" ".join(doc[i].get_textpage().get_text_range() for i in range(len(doc))).split())
        doc.close()
        self.assertIn("Check match", text)
        self.assertIn("read with low confidence", text)

    def test_confirming_the_line_by_hand_settles_it(self):
        from app.models.medicine_model import update_prescription_medicine_match
        from app.db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT medicine_id FROM Prescription_Medicines WHERE pm_id = %s", (self.shaky,))
        medicine_id = cur.fetchone()[0]
        cur.close()
        conn.close()
        update_prescription_medicine_match(self.shaky, medicine_id)
        line = self.data()[self.shaky]
        self.assertFalse(line["safety"]["ocr_uncertain"])
        self.assertEqual(line["status"], "Confirmed")

    def test_lines_with_no_stored_ocr_text_are_not_flagged(self):
        # manually added lines have no OCR line behind them
        from app.models.prescription_model import save_ocr_result
        extra = self.accounts.line(self.pid, "Pantop 40 Tablet", raw_text="added by hand")
        self.assertFalse(self.data()[extra]["safety"]["ocr_uncertain"])
        self.assertIsNotNone(save_ocr_result)


if __name__ == "__main__":
    unittest.main()
