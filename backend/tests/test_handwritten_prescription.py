"""
A real handwritten prescription (five medicine lines in English, a Hindi note, an instruction) taken through the actual pipeline.

The OCR text below is NOT invented: it is what Google Vision returned for the photograph, captured twice on 2026-10-18 - once asking for English
only (as the app did before) and once asking for English and Hindi. The matcher, the instruction reader, the safety annotations and the PDF
are the real ones, run against the real medicine dataset. Only the call to Vision is replaced by that captured output.

What this proves, and what it does not:
  - proves: nothing on this page is confirmed by text similarity; the Hindi note is no longer a sixth medicine; the schedules written as 0-1-0,
    "100" (a misread 1-0-0) and "once in a week" are read as schedules, never as strengths; an instruction is not a medicine; the one product whose
    name is in the dataset is SUGGESTED, the four brands that are not in the dataset are not; manual entry, the PDF and the allergy notice work.
  - does NOT prove the handwriting was read correctly. "Lincont" may well be another brand (a reader sees "Zinconit"): the system cannot tell,
    and says so by leaving it unconfirmed.
"""
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import cv2
import numpy as np

from tests import helpers

ENGLISH_LINES = [
    ("MEDICAL ADVISE :", 0.9888, False), ("2TTE 2016 OTG", 0.3515, True), ("T Lincont 100", 0.6269, False), ("x30dys", 0.534, True),
    ("T shel cal soong 0-1-0", 0.6952, True), ("730", 0.7971, False), ("Tap D - risl 60 k", 0.6121, True), ("Once in a week f Sweets", 0.712, True),
    ("T. Linogen . XT", 0.8252, False), ("X 30d", 0.8657, False), ("T. pan - D 100", 0.6533, True), ("X - 7 dys", 0.48, True),
    ("#xillary temperature monitoring", 0.8603, False), ("Signath Prashanth Mreated Dobe S Patil , MD", 0.8052, True),
    ("Signature Consultant KMC of Superintendent Regn General . No : Medicine 91823 of", 0.9827, False), ("SBMJ Hospital", 0.9801, False),
]
HINDI = "सुबह खाने बाद"            # the Hindi note, as Vision returned it
HINDI_LINES = [(HINDI, 0.8859, False) if text == "2TTE 2016 OTG" else (text, conf, unc) for text, conf, unc in ENGLISH_LINES]


def ocr(lines):
    return {
        "text": "\n".join(t for t, _, _ in lines), "provider": "test", "readable": True, "confidence": 0.77,
        "lines": [{"text": t, "confidence": c, "uncertain": u} for t, c, u in lines],
    }


def png_bytes():
    rng = np.random.default_rng(7)
    image = np.full((900, 700, 3), 235, np.uint8)
    cv2.putText(image, "ABC", (60, 200), cv2.FONT_HERSHEY_SIMPLEX, 3, (30, 30, 30), 6)
    image = cv2.add(image, rng.integers(0, 12, image.shape, dtype=np.uint8))
    return cv2.imencode(".png", image)[1].tobytes()


def pdf_text(app, prescription_id):
    import pypdfium2 as pdfium
    from app.models.prescription_model import get_prescription_by_id
    from app.services.smart_report_service import build_report_pdf
    tmp = tempfile.mkdtemp()
    try:
        path = os.path.join(tmp, "r.pdf")
        with app.app_context():
            build_report_pdf(prescription_id, get_prescription_by_id(prescription_id), path)
        doc = pdfium.PdfDocument(path)
        text = " ".join(" ".join(doc[i].get_textpage().get_text_range() for i in range(len(doc))).split())
        doc.close()
        return text
    finally:
        shutil.rmtree(tmp, True)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.client = cls.app.test_client()
        cls.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        with cls.app.app_context():
            cls.uid = cls.accounts.user(allergies=cls.allergies)
            cls.other = cls.accounts.user(allergies=[])
            cls.h = {"Authorization": f"Bearer {create_access_token(identity=str(cls.uid))}"}
            cls.h_other = {"Authorization": f"Bearer {create_access_token(identity=str(cls.other))}"}

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.accounts.cleanup()

    @classmethod
    def upload(cls, lines):
        with mock.patch("app.routes.prescriptions.extract_text", return_value=ocr(lines)):
            r = cls.client.post("/api/prescriptions/upload", headers=cls.h, data={"file": (io.BytesIO(png_bytes()), "p.png")}, content_type="multipart/form-data")
        assert r.status_code == 201, r.get_data(as_text=True)
        body = r.get_json()
        cls.accounts.prescription_ids.append(body["prescription_id"])
        return body

    def stored(self, prescription_id):
        r = self.client.get(f"/api/prescriptions/{prescription_id}", headers=self.h)
        self.assertEqual(r.status_code, 200)
        return r.get_json()

    @staticmethod
    def line(body, needle):
        found = [m for m in body["detected_medicines"] if needle.lower() in m["raw_text"].lower()]
        assert len(found) == 1, f"{needle!r}: {[m['raw_text'] for m in body['detected_medicines']]}"
        return found[0]


class Pipeline(Base):
    """Upload the captured OCR output through the real route, then read what the screen reloads and what the PDF is given."""

    allergies = []

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hindi_upload = cls.upload(HINDI_LINES)
        cls.english_upload = cls.upload(ENGLISH_LINES)

    def setUp(self):
        self.hindi = self.stored(self.hindi_upload["prescription_id"])
        self.english = self.stored(self.english_upload["prescription_id"])

    # ---- how many medicines, and which ------------------------------------------------------------------------------------------

    def test_the_vision_request_asks_for_english_and_hindi(self):
        from app.services import cloud_ocr_service
        self.assertEqual(cloud_ocr_service.LANGUAGE_HINTS, ["en", "hi"])
        captured = {}

        def fake_post(url, params=None, json=None, timeout=None):
            captured["body"] = json
            return mock.Mock(status_code=200, json=lambda: {"responses": [{"fullTextAnnotation": {"pages": []}}]})
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "x.png")
        with open(path, "wb") as handle:
            handle.write(png_bytes())
        with mock.patch("app.config.Config.GOOGLE_VISION_API_KEY", "test-key-not-real"), mock.patch("app.services.cloud_ocr_service.requests.post", side_effect=fake_post):
            try:
                cloud_ocr_service.extract_words(path, "png")
            except cloud_ocr_service.CloudOcrError:
                pass                                              # an empty page may be refused; the request is what is checked
        self.assertEqual(captured["body"]["requests"][0]["imageContext"]["languageHints"], ["en", "hi"])

    def test_exactly_five_medicine_lines_when_the_hindi_note_is_read_as_hindi(self):
        raws = [m["raw_text"] for m in self.hindi["detected_medicines"]]
        self.assertEqual(len(raws), 5, raws)
        self.assertEqual([r for r in raws if "2TTE" in r or "2016" in r], [])

    def test_the_old_english_only_reading_of_the_note_is_never_a_medicine_match(self):
        gibberish = self.line(self.english, "2TTE")
        self.assertEqual(gibberish["match_status"], "needs_verification")
        self.assertIsNone(gibberish["medicine_id"])
        self.assertFalse(gibberish["suggested"])
        self.assertEqual(gibberish["closest_guesses"], [])
        self.assertTrue(gibberish["verification_label"].startswith("Not identified yet"))

    def test_an_instruction_is_not_a_medicine_and_is_listed_as_a_note(self):
        for body in (self.hindi, self.english):
            self.assertEqual([m for m in body["detected_medicines"] if "monitoring" in m["raw_text"].lower()], [])
        notes = {n["text"]: n for n in self.hindi["notes"]}
        self.assertEqual(notes["#xillary temperature monitoring"]["kind"], "instruction")
        self.assertEqual(notes[HINDI]["kind"], "hindi_note")
        self.assertEqual(notes[HINDI]["possible_meaning"], "morning, after food")
        self.assertEqual(len(self.hindi["notes"]), 2)
        self.assertEqual([n["kind"] for n in self.hindi_upload["notes"]], ["hindi_note", "instruction"], "the upload response carries them too")

    # ---- nothing is confirmed by similarity -----------------------------------------------------------------------------------------

    def test_no_line_is_matched_or_confirmed_and_nothing_is_priced_compared_or_safety_checked(self):
        for m in self.hindi["detected_medicines"]:
            self.assertEqual(m["match_status"], "needs_verification", m["raw_text"])
            self.assertIsNone(m["medicine_id"], m["raw_text"])
            self.assertIsNone(m["offers"], m["raw_text"])
            self.assertEqual(m["interaction_status"], "interaction_data_not_available", m["raw_text"])
            self.assertIsNone(m["allergy_alert_text"], m["raw_text"])
        self.assertEqual(self.hindi["price_comparison"], [])
        self.assertEqual(self.hindi["recommendations"], [])
        self.assertEqual([f for f in self.hindi["clinical_analysis"]["findings"] if f.get("medicines_involved")], [])

    def test_look_alike_names_are_shown_as_candidates_with_a_reason_never_as_a_suggestion(self):
        for needle, wrong in (("Lincont", "Lincer"), ("Linogen", "Linox"), ("shel cal", "Sheltral")):
            line = self.line(self.hindi, needle)
            names = [g["medicine_name"] for g in line["closest_guesses"]]
            self.assertFalse(line["suggested"], needle)
            self.assertTrue(any(wrong in n for n in names), (needle, names))
            self.assertTrue(any("not the same" in r for r in line["verification_reasons"]), (needle, line["verification_reasons"]))

    def test_a_brand_that_is_not_in_the_dataset_says_so(self):
        line = self.line(self.hindi, "risl")
        self.assertEqual(line["closest_guesses"], [])
        self.assertIn("brand may not be in the dataset", " ".join(line["verification_reasons"]))

    def test_the_one_name_that_is_in_the_dataset_is_suggested_but_not_confirmed(self):
        line = self.line(self.hindi, "pan")
        self.assertEqual(line["match_status"], "needs_verification")
        self.assertIsNone(line["medicine_id"])
        self.assertTrue(line["suggested"])
        self.assertEqual(line["suggestion"]["medicine_name"], "Pan-D Capsule PR")
        self.assertTrue(line["verification_label"].startswith("Suggested: Pan-D Capsule PR"))
        self.assertEqual([m["raw_text"] for m in self.hindi["detected_medicines"] if m["suggested"]], [line["raw_text"]])

    # ---- schedules, durations, strengths ----------------------------------------------------------------------------------------

    def test_schedules_and_durations_are_read_as_written_and_nothing_is_invented(self):
        shelcal = self.line(self.hindi, "shel cal")["instructions"]
        self.assertEqual((shelcal["schedule"], shelcal["schedule_certainty"], shelcal["slots"]["afternoon"]), ("0-1-0", "written", 1.0))
        lincont = self.line(self.hindi, "Lincont")["instructions"]
        self.assertEqual((lincont["schedule"], lincont["schedule_certainty"], lincont["duration"]), ("1-0-0", "digits_run_together", "30 days"))
        pan = self.line(self.hindi, "pan")["instructions"]
        self.assertEqual((pan["schedule"], pan["schedule_certainty"], pan["duration"]), ("1-0-0", "digits_run_together", "7 days"))
        rise = self.line(self.hindi, "risl")["instructions"]
        self.assertIn("once weekly", rise["text"].lower())
        self.assertIsNone(rise["duration"], "'f Sweets' is not read as eight weeks")
        linogen = self.line(self.hindi, "Linogen")["instructions"]
        self.assertIsNone(linogen["schedule"], "a schedule the OCR did not return is not guessed")
        self.assertEqual(linogen["duration"], "30 days")

    def test_misread_schedule_digits_are_a_schedule_never_a_strength(self):
        for needle in ("Lincont", "pan"):
            line = self.line(self.hindi, needle)
            self.assertIsNone(line["medicine_id"], needle)
            self.assertIsNone(line["display_strength"], needle)
            self.assertIn("digits were read as", line["instructions"]["text"])

    # ---- the report, the allergy notice, the PDF ---------------------------------------------------------------------------------

    def test_the_allergy_notice_says_the_check_did_not_run_when_none_are_saved(self):
        for check in (self.hindi["allergy_check"], self.hindi_upload["allergy_check"]):
            self.assertIs(check["declared"], False)
            self.assertIn("did not run", check["message"])
            self.assertIn("does NOT mean no allergy was found", check["message"])

    def test_the_pdf_says_what_the_screen_says(self):
        text = pdf_text(self.app, self.hindi_upload["prescription_id"])
        medicines = text.split("Doctor prescribed medicines")[1].split("Medicine timeline")[0]
        self.assertIn("Suggested: Pan-D Capsule PR", medicines)
        self.assertEqual(medicines.count("Needs verification"), 4)
        self.assertNotIn("Matched", medicines)
        self.assertIn("Closest look-alikes (not confirmed): Lincer 100mg Tablet", medicines)
        self.assertIn("Other instructions on the prescription (not medicines)", text)
        self.assertIn("#xillary temperature monitoring", text)
        self.assertIn("morning, after food", text)
        self.assertIn("Allergy check: No allergies are saved on your account, so the allergy check did not run", text)
        self.assertIn("5 detected · 0 matched or confirmed · 5 need checking", text)


class ManualEntry(Base):
    """Typing in a medicine the dataset does not have: stored as typed, never matched, priced or safety-checked."""

    allergies = ["Penicillin"]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pid = cls.upload(HINDI_LINES)["prescription_id"]

    def body(self):
        return self.stored(self.pid)

    def pm(self, needle):
        return self.line(self.body(), needle)

    def post(self, pm_id, payload, headers=None):
        return self.client.post(f"/api/prescriptions/{self.pid}/medicines/{pm_id}/details", json=payload, headers=headers or self.h)

    def test_a_typed_medicine_is_kept_as_entered_by_you_and_is_never_matched_priced_or_checked(self):
        line = self.pm("shel cal")
        rows_before = len(self.body()["detected_medicines"])
        r = self.post(line["pm_id"], {"name": "Shelcal Strong", "strength": "500 mg", "form": "Tablet", "schedule": "0-1-0", "duration": "30 days"})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = self.body()
        got = self.line(body, "shel cal")
        self.assertEqual(got["verification_status"], "entered_by_user")
        self.assertEqual(got["user_entered"], {"name": "Shelcal Strong", "strength": "500 mg", "form": "Tablet", "schedule": "0-1-0", "duration": "30 days"})
        self.assertIsNone(got["medicine_id"])
        self.assertEqual(got["raw_text"], "T shel cal soong 0-1-0", "the line keeps what was read")
        self.assertTrue(got["closest_guesses"], "the look-alikes it was shown are kept")
        self.assertEqual((got["instructions"]["schedule"], got["instructions"]["duration"]), ("0-1-0", "30 days"))
        self.assertTrue(got["verification_label"].startswith("Entered by you"))
        self.assertIsNone(got["offers"])
        self.assertEqual(len(body["detected_medicines"]), rows_before)
        self.assertEqual(body["price_comparison"], [])
        self.assertEqual(body["recommendations"], [])
        self.assertEqual([f for f in body["clinical_analysis"]["findings"] if f.get("medicines_involved")], [])

    def test_an_audit_row_records_what_was_entered_and_what_the_person_was_looking_at(self):
        line = self.pm("Linogen")
        self.assertEqual(self.post(line["pm_id"], {"name": "Linogen XT", "form": "Tablet", "schedule": "1-0-0", "duration": "x 30 days"}).status_code, 200)
        log = self.client.get(f"/api/prescriptions/{self.pid}/verification-log", headers=self.h).get_json()
        mine = [d for d in log["decisions"] if d["pm_id"] == line["pm_id"]]
        self.assertEqual(mine[-1]["decision"], "entered_by_user")
        self.assertEqual(mine[-1]["raw_text"], "T. Linogen . XT")
        self.assertEqual(mine[-1]["previous_status"], "needs_verification")
        self.assertEqual(mine[-1]["entered"]["name"], "Linogen XT")
        got = self.pm("Linogen")
        self.assertEqual((got["instructions"]["schedule"], got["instructions"]["duration"]), ("1-0-0", "30 days"), "'x 30 days' typed with an x is read")

    def test_bad_input_is_refused_with_a_reason_and_changes_nothing(self):
        line = self.pm("Lincont")
        cases = [({}, "required"), ({"name": "x"}, "required"), ({"name": "A" * 101}, "at most"), ({"name": "Ok", "form": "Rocket"}, "Form must be one of"),
                 ({"name": "Ok", "strength": "9" * 41}, "at most"), ({"name": 5}, "must be text"), ({"name": "Ok", "schedule": "s" * 101}, "at most")]
        for payload, words in cases:
            r = self.post(line["pm_id"], payload)
            self.assertEqual(r.status_code, 400, payload)
            self.assertIn(words, r.get_json()["error"])
        not_json = self.client.post(f"/api/prescriptions/{self.pid}/medicines/{line['pm_id']}/details", data="not json", headers=self.h)
        self.assertEqual(not_json.status_code, 400)
        self.assertEqual(self.pm("Lincont")["verification_status"], "pending_verification")

    def test_it_needs_a_login_and_the_owner(self):
        line = self.pm("Lincont")
        self.assertEqual(self.client.post(f"/api/prescriptions/{self.pid}/medicines/{line['pm_id']}/details", json={"name": "Ok"}).status_code, 401)
        self.assertEqual(self.post(line["pm_id"], {"name": "Ok"}, headers=self.h_other).status_code, 404)
        self.assertEqual(self.post(999999999, {"name": "Ok"}).status_code, 404)
        self.assertEqual(self.pm("Lincont")["verification_status"], "pending_verification")

    def test_control_characters_are_flattened_and_markup_is_stored_inertly(self):
        line = self.pm("risl")
        self.assertEqual(self.post(line["pm_id"], {"name": "D-Rise\n60K\t<b>x</b>", "form": "Capsule", "schedule": "once weekly", "duration": "8 weeks"}).status_code, 200)
        got = self.pm("risl")
        self.assertEqual(got["user_entered"]["name"], "D-Rise 60K <b>x</b>")
        self.assertIn("once weekly", got["instructions"]["text"].lower())
        self.assertEqual(got["instructions"]["duration"], "8 weeks")

    def test_the_pdf_shows_the_typed_medicine_as_entered_by_you_with_the_allergy_notice(self):
        line = self.pm("shel cal")
        if line["verification_status"] != "entered_by_user":
            self.assertEqual(self.post(line["pm_id"], {"name": "Shelcal Strong", "strength": "500 mg", "form": "Tablet", "schedule": "0-1-0", "duration": "30 days"}).status_code, 200)
        text = pdf_text(self.app, self.pid)
        self.assertIn("Shelcal Strong", text)
        self.assertIn("Entered by you", text)
        self.assertIn("Not matched to the dataset: no price, saving or safety check is shown for it.", text)
        self.assertIn("500 mg Tablet", text)
        self.assertIn("compared the medicines you confirmed with the 1 allergy", text)
        self.assertNotIn("did not run", text, "an allergy WAS saved, so the notice must not say the check did not run")


class NotesAndEntryRules(unittest.TestCase):
    """The pure rules, with no database."""

    def setUp(self):
        from app.services import manual_entry_service, prescription_notes_service
        self.notes, self.entry = prescription_notes_service, manual_entry_service

    def lines(self, *texts):
        return [{"text": t, "confidence": 0.9, "uncertain": False} for t in texts]

    def test_a_line_that_starts_like_a_medicine_is_never_a_note(self):
        got = self.notes.notes_from_ocr_lines(self.lines("T. Review cream", "Tab Check 500", "Cap. Monitor", "Syp avoid", "Inj. follow"))
        self.assertEqual(got, [])

    def test_a_recorded_vitals_line_is_not_an_instruction_but_monitoring_is(self):
        got = self.notes.notes_from_ocr_lines(self.lines("BP 120/80 temperature 98.6", "Sugar fasting 90", "temperature monitoring", "Review after 1 week", "Avoid cold drinks"))
        self.assertEqual([n["text"] for n in got], ["temperature monitoring", "Review after 1 week", "Avoid cold drinks"])
        self.assertTrue(all(n["kind"] == "instruction" for n in got))

    def test_headers_and_dosing_lines_are_not_notes(self):
        self.assertEqual(self.notes.notes_from_ocr_lines(self.lines("MEDICAL ADVISE :", "Once in a week x 8 weeks", "x30dys", "1-0-0", "SBMJ Hospital")), [])

    def test_hindi_is_translated_only_when_every_word_is_known(self):
        meaning = self.notes.hindi_meaning
        self.assertEqual(meaning("सुबह खाने बाद"), "morning, after food")
        self.assertEqual(meaning("सुबह खाने के बाद"), "morning, after food")
        self.assertEqual(meaning("रात"), "night")
        self.assertEqual(meaning("खाली पेट"), "on an empty stomach")
        self.assertIsNone(meaning("सुबह खाने बाद दवा लें"), "an unknown word means no translation")
        self.assertIsNone(meaning("दवा"))
        self.assertIsNone(meaning(""))

    def test_a_hindi_note_is_shown_as_read_even_without_a_translation(self):
        got = self.notes.notes_from_ocr_lines(self.lines("दवा लें"))
        self.assertEqual((got[0]["kind"], got[0]["text"], got[0]["possible_meaning"]), ("hindi_note", "दवा लें", None))

    def test_entry_validation(self):
        ok = self.entry.validate({"name": "  Zinconit \n 500 ", "strength": " 500 mg ", "form": "Tablet", "schedule": "", "duration": None})
        self.assertEqual(ok, {"name": "Zinconit 500", "strength": "500 mg", "form": "Tablet", "schedule": None, "duration": None})
        for bad in (None, [], "x", {"name": ""}, {"name": "a"}, {"name": "ok", "form": "Rocket"}, {"name": 3}, {"name": "ok", "strength": "x" * 41}):
            with self.assertRaises(ValueError, msg=bad):
                self.entry.validate(bad)

    def test_merging_keeps_the_stored_lookalikes_and_decoding_reads_them_back(self):
        stored = json.dumps({"kind": "closest_guesses", "candidates": [{"medicine_id": 1, "medicine_name": "Lincer", "score": 0.8}]})
        details = {"name": "Zinconit", "strength": None, "form": "Tablet", "schedule": "1-0-0", "duration": "30 days"}
        merged = json.loads(self.entry.merge_into_options(stored, details))
        self.assertEqual(merged["candidates"][0]["medicine_name"], "Lincer")
        self.assertEqual(merged["user_entered"], {"name": "Zinconit", "strength": None, "form": "Tablet"})
        self.assertEqual(self.entry.decode(merged), {"name": "Zinconit", "strength": None, "form": "Tablet"})
        for other in (None, "", "not json", json.dumps([{"medicine_id": 3}]), json.dumps({"kind": "other"})):
            self.assertEqual(json.loads(self.entry.merge_into_options(other, details))["candidates"], [])
        self.assertIsNone(self.entry.decode(None))
        self.assertIsNone(self.entry.decode("garbage"))


if __name__ == "__main__":
    unittest.main()
