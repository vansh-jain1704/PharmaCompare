"""
Photo-quality warnings: they say WHY a photo is likely to read badly, only ever warn, and never block an upload or touch the OCR.
Images are generated here (a clean synthetic page and degraded copies of it); no real prescription is used.
"""
import io
import os
import tempfile
import unittest
from unittest import mock

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from tests import helpers


def page(width=1100, height=900):
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 38)
    except OSError:
        font = ImageFont.load_default()
    for i, line in enumerate(("1.  Tab Dolo 650   1-0-1   for 5 days", "2.  Tab Azee 500   1-0-0   for 3 days", "3.  Cap Omez 20   1-0-0   for 7 days")):
        draw.text((60, 120 + i * 120), line, fill=(0, 0, 0), font=font)
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def write(image, suffix=".png"):
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    handle.close()
    cv2.imwrite(handle.name, image)
    return handle.name


class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.services import image_quality_service
        cls.q = image_quality_service
        cls.base = page()

    def codes(self, image):
        path = write(image)
        self.addCleanup(os.unlink, path)
        return [w["code"] for w in self.q.assess(path, "png")["warnings"]]

    def test_a_clean_sharp_well_lit_page_has_no_warnings(self):
        self.assertEqual(self.codes(self.base), [])

    def test_a_blurred_photo_is_flagged_as_blurry(self):
        self.assertIn("blurry", self.codes(cv2.GaussianBlur(self.base, (0, 0), 4)))
        self.assertIn("blurry", self.codes(cv2.GaussianBlur(self.base, (0, 0), 8)))

    def test_a_dark_photo_is_flagged_dark_and_low_in_contrast(self):
        codes = self.codes((self.base * 0.25).astype(np.uint8))
        self.assertIn("too_dark", codes)
        self.assertIn("low_contrast", codes)

    def test_faint_writing_is_flagged_as_low_contrast(self):
        faded = (128 + (self.base.astype(np.int16) - 128) * 0.15).astype(np.uint8)
        self.assertIn("low_contrast", self.codes(faded))

    def test_a_small_image_is_flagged_as_low_resolution(self):
        small = cv2.resize(self.base, (250, 204))
        self.assertIn("low_resolution", self.codes(small))

    def test_every_warning_says_what_to_do_in_plain_words(self):
        path = write((self.base * 0.2).astype(np.uint8))
        self.addCleanup(os.unlink, path)
        for w in self.q.assess(path, "png")["warnings"]:
            self.assertGreater(len(w["text"]), 40)
            self.assertRegex(w["text"], r"(?i)retake|photo|take|hold")

    def test_the_result_states_what_was_checked_and_the_measurements(self):
        path = write(self.base)
        self.addCleanup(os.unlink, path)
        a = self.q.assess(path, "png")
        self.assertEqual(a["checked"], ["size", "sharpness", "brightness", "contrast"])
        self.assertEqual((a["width"], a["height"]), (1100, 900))
        self.assertGreater(a["sharpness"], 100)

    def test_a_file_that_is_not_an_image_claims_nothing(self):
        handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        handle.write(b"this is not an image")
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        self.assertIsNone(self.q.assess(handle.name, "png"))
        self.assertIsNone(self.q.assess(os.path.join(tempfile.gettempdir(), "zz_missing_file.png"), "png"))

    def test_the_thresholds_are_the_documented_configurable_defaults(self):
        from app.config import Config
        self.assertEqual((Config.IMAGE_MIN_SIDE_PIXELS, Config.IMAGE_MIN_SHARPNESS, Config.IMAGE_MIN_BRIGHTNESS, Config.IMAGE_MIN_CONTRAST), (600, 20.0, 70.0, 15.0))
        with mock.patch.object(Config, "IMAGE_MIN_SHARPNESS", 1e9):
            self.assertIn("blurry", self.codes(self.base))                      # the setting is honoured

    def test_the_documentation_states_the_calibration_and_its_limit(self):
        doc = " ".join(self.q.__doc__.split())              # the text wraps across lines
        self.assertIn("five distinct sample photos", doc)
        self.assertIn("Five photos cannot validate a threshold", doc)
        self.assertIn("only ever WARN", doc)


class ThroughTheRoutes(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.client = self.app.test_client()
        self.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        with self.app.app_context():
            self.uid = self.accounts.user(allergies=[])
            self.h = {"Authorization": f"Bearer {create_access_token(identity=str(self.uid))}"}
        self.base = page()

    def tearDown(self):
        with self.app.app_context():
            self.accounts.cleanup()

    def upload(self, image, readable=True):
        ok = {"text": "Tab Dolo 650", "lines": [{"text": "Tab Dolo 650", "confidence": 0.95, "uncertain": False}], "confidence": 0.95 if readable else 0.1,
              "readable": readable, "provider": "test"}
        ok["readable"] = readable
        ok_bytes = cv2.imencode(".png", image)[1].tobytes()
        with mock.patch("app.routes.prescriptions.extract_text", return_value=ok):
            return self.client.post("/api/prescriptions/upload", headers=self.h, data={"file": (io.BytesIO(ok_bytes), "photo.png")}, content_type="multipart/form-data")

    def test_a_blurry_upload_still_succeeds_and_carries_the_warnings(self):
        r = self.upload(cv2.GaussianBlur(self.base, (0, 0), 6))
        self.assertEqual(r.status_code, 201)                                   # a warning never blocks
        quality = r.get_json()["image_quality"]
        self.assertIn("blurry", [w["code"] for w in quality["warnings"]])
        self.assertEqual(quality["checked"], ["size", "sharpness", "brightness", "contrast"])

    def test_a_clean_upload_carries_the_measurements_and_no_warnings(self):
        quality = self.upload(self.base).get_json()["image_quality"]
        self.assertEqual(quality["warnings"], [])

    def test_the_unreadable_response_explains_what_to_fix(self):
        r = self.upload(cv2.GaussianBlur(self.base, (0, 0), 6), readable=False)
        self.assertEqual(r.status_code, 422)
        body = r.get_json()
        self.assertEqual(body["status"], "needs_reupload")
        self.assertIn("blurry", [w["code"] for w in body["image_quality"]["warnings"]])

    def test_the_ocr_text_is_whatever_the_ocr_returned_the_check_changes_nothing(self):
        body = self.upload(cv2.GaussianBlur(self.base, (0, 0), 6)).get_json()
        self.assertEqual(body["extracted_text"], "Tab Dolo 650")
        self.assertEqual(body["lines"][0]["text"], "Tab Dolo 650")

    def test_the_detail_derives_the_check_from_the_stored_photo(self):
        from app.models.prescription_model import create_prescription
        path = write(cv2.GaussianBlur(self.base, (0, 0), 6))
        self.addCleanup(os.unlink, path)
        with self.app.app_context():
            pid = create_prescription(self.uid, path, status="processed")
            self.accounts.prescription_ids.append(pid)
        body = self.client.get(f"/api/prescriptions/{pid}", headers=self.h).get_json()
        self.assertIn("blurry", [w["code"] for w in body["image_quality"]["warnings"]])

    def test_a_prescription_whose_photo_is_gone_claims_nothing(self):
        with self.app.app_context():
            pid = self.accounts.prescription(self.uid)                        # points at a file that does not exist
        body = self.client.get(f"/api/prescriptions/{pid}", headers=self.h).get_json()
        self.assertIsNone(body["image_quality"])


if __name__ == "__main__":
    unittest.main()
