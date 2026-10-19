"""
Dosing instructions, the Medicine Timeline and combination-strength display.

The OCR lines below are the text of a real handwritten prescription as the OCR returned it (medicine and dosing lines only).
Handwriting made "1-0-0" come back as "100" and put each duration on a separate line below its medicine.
"""
import unittest

from tests import helpers

# a real handwritten page, as returned by OCR (header, signature and clinic lines left out)
REAL_LINES = [
    "MEDICAL ADVISE :", "2TTE 2016 OTG", "T Lincont 100", "x30dys", "T shel cal soong 0-1-0", "730", "Tap D - risl 60 k",
    "Once in a week f Sweets", "T. Linogen . XT", "X 30d", "T. pan - D 100", "X - 7 dys", "#xillary temperature monitoring",
]
MEDICINES = ["2TTE 2016 OTG", "T Lincont 100", "T shel cal soong 0-1-0", "Tap D - risl 60 k", "T. Linogen . XT", "T. pan - D 100"]


class Parse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.services import instruction_service
        cls.ins = instruction_service

    def test_written_schedules_including_ocr_confusions(self):
        for text, schedule, freq in (("1-0-1", "1-0-1", "Twice daily"), ("1 - 0 - 1", "1-0-1", "Twice daily"), ("l-0-l", "1-0-1", "Twice daily"),
                                     ("O-1-O", "0-1-0", "Once daily"), ("1-1-1", "1-1-1", "3 times daily"), ("1-0-0-1", "1-0-0-1", "Twice daily"),
                                     ("1/2-0-1/2", "1/2-0-1/2", "Twice daily")):
            p = self.ins.parse(f"Tab Dolo 650 {text}")
            self.assertEqual((p["schedule"], p["schedule_certainty"], p["frequency"]), (schedule, "written", freq), text)

    def test_slots_follow_the_written_schedule(self):
        p = self.ins.parse("1-0-1")
        self.assertEqual(p["slots"], {"morning": 1.0, "afternoon": 0.0, "night": 1.0})
        self.assertEqual(self.ins.parse("1-0-0-1")["slots"], {"morning": 1.0, "afternoon": 0.0, "evening": 0.0, "night": 1.0})
        self.assertEqual(self.ins.describe_schedule(p), "1-0-1: morning and night")

    def test_digits_that_ran_together_are_only_possibly_a_schedule(self):
        p = self.ins.parse("T Lincont 100")
        self.assertEqual((p["schedule"], p["schedule_certainty"]), ("1-0-0", "digits_run_together"))
        text = self.ins.describe_schedule(p)
        self.assertTrue(text.startswith("possibly 1-0-0"))
        self.assertIn("check the prescription", text)
        self.assertTrue(self.ins.describe_schedule(p, short=True).startswith("Possibly 1-0-0"))

    def test_a_strength_or_a_number_with_a_unit_is_never_a_schedule(self):
        for text in ("Tab Zerodol-P 100 mg", "Syp 100 ml", "Tab Eltroxin 100mcg", "Tab Dolo 650", "Tab Telma 40", "T. Linogen . XT", "Tab 1000 mg", "Tab Foo 1001"):
            self.assertIsNone(self.ins.parse(text)["schedule"], text)

    def test_a_product_that_owns_the_number_makes_it_a_strength_not_a_schedule(self):
        p = self.ins.parse("T Lincont 100")
        self.assertIsNone(self.ins.drop_schedule_that_is_a_strength(p, {"100"})["schedule"])
        self.assertEqual(self.ins.drop_schedule_that_is_a_strength(p, {"30", "40"})["schedule"], "1-0-0")
        written = self.ins.parse("Tab X 1-0-0")
        self.assertEqual(self.ins.drop_schedule_that_is_a_strength(written, {"100"})["schedule"], "1-0-0")   # a WRITTEN schedule is kept
        self.assertEqual(self.ins.owned_numbers({"medicine_name": "Lincer 100mg Tablet", "composition": "Sertraline (100mg)", "strength": "100mg"}), {"100"})

    def test_durations_as_handwritten_and_as_ocr_returns_them(self):
        for text, expected, days in (("x30dys", "30 days", 30), ("X 30d", "30 days", 30), ("X - 7 dys", "7 days", 7), ("x 5 days", "5 days", 5),
                                     ("for 10 days", "10 days", 10), ("5 days", "5 days", 5), ("x 8 weeks", "8 weeks", 56), ("for 2 weeks", "2 weeks", 14),
                                     ("x 1 month", "1 month", 30), ("1. Tab Dolo 650 1-0-1 × 5 days", "5 days", 5), ("x1 day", "1 day", 1)):
            p = self.ins.parse(text)
            self.assertEqual((p["duration"], p["duration_days"]), (expected, days), text)

    def test_a_duration_whose_number_is_unreadable_is_said_to_be_unreadable(self):
        for text in ("Tab . Dolo 650 X sdays .", "Tab . Azee - 040 500 x #days"):
            p = self.ins.parse(text)
            self.assertTrue(p["duration_unreadable"], text)
            self.assertIsNone(p["duration"])
        self.assertFalse(self.ins.parse("x30dys")["duration_unreadable"])
        self.assertFalse(self.ins.parse("Tab Dolo 650")["duration_unreadable"])

    def test_words_dose_and_timing(self):
        p = self.ins.parse("Syp Paracetamol 5 ml TDS after food x 3 days")
        self.assertEqual((p["frequency"], p["dose"], p["timing"], p["duration"]), ("3 times daily", "5 ml", "after food", "3 days"))
        self.assertEqual(self.ins.parse("Once in a week f Sweets")["frequency"], "Once weekly")
        self.assertEqual(self.ins.parse("Dolo 650 SOS")["frequency"], "As needed")
        self.assertEqual(self.ins.parse("Taban ( B / F ) - 100 D")["timing"], "before food")
        self.assertEqual(self.ins.parse("1/2 tab 0-0-1")["dose"], "1/2 tablet")

    def test_an_explicit_weekly_note_outranks_digits_that_only_look_like_a_schedule(self):
        p = self.ins.parse("Cap D3 60K 100 once in a week")
        self.assertEqual(p["frequency"], "Once weekly")

    def test_nothing_is_invented_for_text_with_no_dosing(self):
        for text in ("", None, "   ", "Tab Dolo 650", "Patient: Demo", "T. Linogen . XT"):
            p = self.ins.parse(text)
            self.assertFalse(self.ins.has_instruction(p), text)

    def test_hindi_morning_after_food_note_is_read_when_the_ocr_returns_it(self):
        p = self.ins.parse("सुबह खाने बाद")
        self.assertEqual(p["timing"], "after food")


class AttachSplitInstructionRows(unittest.TestCase):
    """OCR returns the instruction below the name as its own line; it belongs to the medicine above it."""

    @classmethod
    def setUpClass(cls):
        from app.services import instruction_service
        cls.attached = instruction_service.attach(MEDICINES, [{"text": t} for t in REAL_LINES], lambda t: True)

    def test_each_duration_is_attached_to_its_own_medicine(self):
        a = self.attached
        self.assertEqual(a["T Lincont 100"]["instructions"]["duration"], "30 days")
        self.assertEqual(a["T Lincont 100"]["sources"], ["T Lincont 100", "x30dys"])
        self.assertEqual(a["T. Linogen . XT"]["instructions"]["duration"], "30 days")
        self.assertEqual(a["T. pan - D 100"]["instructions"]["duration"], "7 days")

    def test_the_weekly_note_goes_to_the_medicine_above_it(self):
        self.assertEqual(self.attached["Tap D - risl 60 k"]["instructions"]["frequency"], "Once weekly")

    def test_a_written_schedule_on_the_medicine_line_is_kept(self):
        a = self.attached["T shel cal soong 0-1-0"]["instructions"]
        self.assertEqual((a["schedule"], a["schedule_certainty"]), ("0-1-0", "written"))
        self.assertIsNone(a["duration"])                    # "730" is not readable as a duration: nothing is guessed

    def test_a_row_is_never_attached_across_another_medicine(self):
        self.assertIsNone(self.attached["T shel cal soong 0-1-0"]["instructions"]["duration"])
        self.assertEqual(self.attached["2TTE 2016 OTG"]["sources"], ["2TTE 2016 OTG"])

    def test_a_line_far_from_any_medicine_is_not_attached(self):
        from app.services import instruction_service as ins
        lines = [{"text": t} for t in ("Tab Dolo 650", "Rx", "Weight 60", "x 5 days")]       # two unrelated lines in between
        got = ins.attach(["Tab Dolo 650"], lines, lambda t: True)
        self.assertIsNone(got["Tab Dolo 650"]["instructions"]["duration"])

    def test_instruction_rows_are_not_attached_before_any_medicine(self):
        from app.services import instruction_service as ins
        got = ins.attach(["Tab Dolo 650"], [{"text": "x 5 days"}, {"text": "Tab Dolo 650"}], lambda t: True)
        self.assertIsNone(got["Tab Dolo 650"]["instructions"]["duration"])


class AnalysisAndStorage(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.accounts = helpers.TempAccounts()
        self.uid = self.accounts.user(allergies=[])
        self.pid = self.accounts.prescription(self.uid)

    def tearDown(self):
        self.accounts.cleanup()
        self.ctx.pop()

    def test_detection_stores_what_the_prescription_wrote_including_rows_split_off_below(self):
        from app.models.medicine_model import get_prescription_medicines
        from app.routes.prescriptions import _run_medicine_detection
        lines = [{"text": t} for t in ("Tab Dolo 650", "x 5 days", "Tab Azee 500 1-0-0 for 3 days", "T Lincont 100", "x30dys")]
        _run_medicine_detection(self.pid, lines)
        by_text = {m["raw_text"]: m for m in get_prescription_medicines(self.pid)}
        self.assertEqual(by_text["Tab Dolo 650"]["duration"], "5 days")                    # from the line below
        self.assertEqual((by_text["Tab Azee 500 1-0-0 for 3 days"]["frequency"], by_text["Tab Azee 500 1-0-0 for 3 days"]["duration"]), ("1-0-0: morning", "3 days"))
        self.assertEqual(by_text["T Lincont 100"]["frequency"], "Possibly 1-0-0 (digits read as 100)")     # never stated as fact
        self.assertEqual(by_text["T Lincont 100"]["duration"], "30 days")

    def test_digits_that_are_the_matched_products_own_strength_are_not_stored_as_a_schedule(self):
        from app.models.medicine_model import get_prescription_medicines
        from app.routes.prescriptions import _run_medicine_detection
        from app.services.medicine_matching_service import match_line
        probe = match_line("Tab Eltroxin 100")
        if probe["status"] != "matched" or "100" not in (probe["medicine"].get("composition") or ""):
            self.skipTest("no matched product with a 100 strength to test with in this dataset")
        _run_medicine_detection(self.pid, [{"text": "Tab Eltroxin 100"}])
        row = get_prescription_medicines(self.pid)[0]
        self.assertFalse((row["frequency"] or "").startswith("Possibly"))

    def test_the_analysis_derives_instructions_for_a_prescription_whose_stored_columns_are_empty(self):
        """An old prescription (analysed before dosing was read): the same text still gives its instructions, nothing is rewritten."""
        from app.models.medicine_model import get_prescription_medicines
        from app.services.medicine_safety_service import annotate
        pm = self.accounts.line(self.pid, "Dolo 650 Tablet", raw_text="1. Tab Dolo 650", status="matched", confidence=1.0)
        ocr = [{"text": "1. Tab Dolo 650", "confidence": 0.9, "uncertain": False}, {"text": "1-0-1 after food x 5 days", "confidence": 0.9, "uncertain": False}]
        row = get_prescription_medicines(self.pid)[0]
        self.assertIsNone(row["frequency"])
        out = annotate([row], [], ocr)[pm]["instructions"]
        self.assertEqual((out["schedule"], out["timing"], out["duration"]), ("1-0-1", "after food", "5 days"))
        self.assertEqual(out["text"], "1-0-1: morning and night")
        self.assertEqual(out["sources"], ["1. Tab Dolo 650", "1-0-1 after food x 5 days"])
        self.assertIsNone(get_prescription_medicines(self.pid)[0]["frequency"])      # nothing was written back

    def test_a_strength_is_not_reported_as_a_schedule_for_an_identified_product(self):
        from app.models.medicine_model import get_prescription_medicines
        from app.services.medicine_safety_service import annotate
        from tests.test_verification_workflow import medicine
        lincer = medicine("Lincer 100mg Tablet")
        pm = self.accounts.line(self.pid, "Lincer 100mg Tablet", raw_text="T Lincer 100", status="user_confirmed", confidence=None)
        out = annotate(get_prescription_medicines(self.pid), [], [{"text": "T Lincer 100"}])[pm]["instructions"]
        self.assertIsNone(out["schedule"])
        self.assertEqual(lincer["medicine_name"], "Lincer 100mg Tablet")


class DigitsThatLookLikeAScheduleDoNotHideTheRightCandidate(unittest.TestCase):
    """
    Handwritten "1-0-0" is often read "100" and then taken for a strength, which can push the right product out of the candidates.
    A second reading puts it back among them, FIRST, with the reason: it never settles the line.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from app.services.medicine_matching_service import match_line
        cls.match_line = staticmethod(match_line)

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def test_the_right_product_is_offered_first_with_the_reason_and_the_line_stays_unsettled(self):
        r = self.match_line("T. pan - D 100")
        self.assertEqual(r["status"], "needs_verification")                      # never settled: the number is what the product contradicts
        self.assertEqual(r["ignored_schedule_digits"], "100")
        self.assertEqual(r["raw_text"], "T. pan - D 100")                        # what was read is never replaced
        first = r["guesses"][0]
        self.assertEqual(first["medicine_name"], "Pan-D Capsule PR")
        self.assertIn("may be a dose schedule (1-0-0)", first["reasons"][0])
        self.assertIn("only you can say", first["reasons"][0])
        self.assertEqual(r["medicine"]["medicine_name"], "Pan-D Capsule PR")
        self.assertLessEqual(len(r["guesses"]), 3)
        self.assertEqual(len({g["medicine_id"] for g in r["guesses"]}), len(r["guesses"]))

    def test_the_form_difference_is_still_stated(self):
        first = self.match_line("T. pan - D 100")["guesses"][0]
        self.assertTrue(any("tablet" in reason and "capsule" in reason for reason in first["reasons"]), first["reasons"])

    def test_a_real_strength_is_still_matched_with_its_number_and_nothing_is_ignored(self):
        r = self.match_line("Tab Lincer 100")
        self.assertEqual((r["status"], r["medicine"]["medicine_name"]), ("matched", "Lincer 100mg Tablet"))
        self.assertNotIn("ignored_schedule_digits", r)

    def test_a_brand_whose_name_carries_a_number_is_never_rescued_by_ignoring_a_number(self):
        for text in ("Tab Azee 500 100", "T Lincont 100"):
            r = self.match_line(text)
            self.assertEqual(r["status"], "needs_verification", text)
            self.assertNotIn("ignored_schedule_digits", r)

    def test_a_product_that_owns_the_number_is_not_treated_as_ignoring_it(self):
        r = self.match_line("Tab Zerodol-P 100")                                  # Zerodol-P has an aceclofenac 100mg
        self.assertNotIn("ignored_schedule_digits", r)

    def test_a_number_with_a_unit_or_a_leading_number_is_not_treated_as_a_schedule(self):
        from app.services.medicine_matching_service import _without_schedule_digits as strip
        for text in ("Tab Zerodol-P 100 mg", "100 Dolo", "Tab Dolo 650", "Tab X 1-0-1", "Tab X 000"):
            self.assertEqual(strip(text), (text, None), text)
        self.assertEqual(strip("T. pan - D 100"), ("T. pan - D", "100"))

    def test_the_candidates_are_stored_and_shown_and_nothing_is_analysed_until_the_person_decides(self):
        from flask_jwt_extended import create_access_token
        from app.models.medicine_model import get_prescription_medicines
        from app.routes.prescriptions import _rerun_analysis, _run_medicine_detection
        accounts = helpers.TempAccounts()
        try:
            uid = accounts.user(allergies=[])
            pid = accounts.prescription(uid)
            _run_medicine_detection(pid, [{"text": "T. pan - D 100"}])
            _rerun_analysis(pid)
            h = {"Authorization": f"Bearer {create_access_token(identity=str(uid))}"}
            body = self.app.test_client().get(f"/api/prescriptions/{pid}", headers=h).get_json()
            line = body["detected_medicines"][0]
            self.assertEqual((line["match_status"], line["medicine_id"]), ("needs_verification", None))
            self.assertEqual(line["closest_guesses"][0]["medicine_name"], "Pan-D Capsule PR")
            self.assertIn("dose schedule", " ".join(line["verification_reasons"]))
            self.assertEqual(body["price_comparison"], [])                      # not priced, not analysed
            self.assertEqual(body["recommendations"], [])
        finally:
            accounts.cleanup()

    def test_a_matched_line_that_relies_on_ignoring_such_digits_is_held_as_check_match(self):
        from flask_jwt_extended import create_access_token
        accounts = helpers.TempAccounts()
        try:
            uid = accounts.user(allergies=[])
            pid = accounts.prescription(uid)
            accounts.line(pid, "Pan-D Capsule PR", raw_text="T. pan - D 100", status="matched", confidence=0.71)
            h = {"Authorization": f"Bearer {create_access_token(identity=str(uid))}"}
            line = self.app.test_client().get(f"/api/prescriptions/{pid}", headers=h).get_json()["detected_medicines"][0]
            self.assertTrue(line["needs_check"])
            self.assertIn("read as a dose schedule (1-0-0), not a strength", line["read_assumption"])
            self.assertEqual(line["verification_status"], "flagged_for_review")
            self.assertEqual(line["instructions"]["schedule_certainty"], "digits_run_together")
        finally:
            accounts.cleanup()


class CombinationStrength(unittest.TestCase):
    def test_every_ingredient_is_shown_with_its_strength(self):
        from app.services.composition import display_strength as d
        self.assertEqual(d("Domperidone (30mg) + Pantoprazole (40mg)", "30mg"), "Domperidone 30mg + Pantoprazole 40mg")
        self.assertEqual(d("Calcium Carbonate (500mg) + Vitamin D3 (2000IU)", "500mg"), "Calcium Carbonate 500mg + Vitamin D3 2000IU")
        self.assertEqual(d("Metformin (500mg)", "500mg"), "500mg")
        self.assertEqual(d("Paracetamol (125mg/5ml)", None), "125mg/5ml")

    def test_unreadable_or_missing_strengths_fall_back_instead_of_being_invented(self):
        from app.services.composition import display_strength as d
        self.assertEqual(d("Glimepiride (NA) + Metformin (NA)", "NA"), "NA")
        self.assertEqual(d("Glimepiride (NA) + Metformin (500mg)", "x"), "x")
        self.assertIsNone(d("", None))
        self.assertEqual(d("garbled text", "10mg"), "10mg")

    def test_the_analysis_carries_it_for_identified_products_only(self):
        from app.services.medicine_safety_service import annotate
        from tests.test_verification_workflow import medicine
        panda = medicine("Pan-D Capsule PR")
        row = {**panda, "pm_id": 1, "raw_text": "Pan-D", "match_status": "user_confirmed", "match_confidence": None, "match_options": None}
        self.assertEqual(annotate([row], [], [])[1]["display_strength"], "Domperidone 30mg + Pantoprazole 40mg")
        unsettled = {"pm_id": 2, "raw_text": "x", "match_status": "needs_verification", "match_confidence": None, "match_options": None, "medicine_id": None, "primary_salt": None}
        self.assertIsNone(annotate([unsettled], [], [])[2]["display_strength"])


class Timeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.services import instruction_service, timeline_service
        cls.t, cls.ins = timeline_service, instruction_service

    def entry(self, pm_id, name, text, identified=True, form="Tablet"):
        parsed = self.ins.parse(text)
        return {"pm_id": pm_id, "raw_text": text, "name": name, "form": form, "identified": identified,
                "instructions": {**parsed, "text": self.ins.describe_schedule(parsed)}}

    def test_times_of_day_come_from_the_written_schedule(self):
        tl = self.t.build_timeline([self.entry(1, "Dolo 650 Tablet", "Tab Dolo 650 1-0-1 x 5 days"), self.entry(2, "Azee 500 Tablet", "Tab Azee 500 1-0-0 for 3 days")])
        by_slot = {s["slot"]: [i["medicine"] for i in s["items"]] for s in tl["slots"]}
        self.assertEqual(by_slot, {"morning": ["Dolo 650 Tablet", "Azee 500 Tablet"], "night": ["Dolo 650 Tablet"]})
        morning = tl["slots"][0]["items"][0]
        self.assertEqual((morning["amount"], morning["duration"], morning["possible"]), ("1 tablet", "for 5 days", False))
        self.assertEqual([s["label"] for s in tl["slots"]], ["Morning", "Night"])

    def test_nothing_is_defaulted_for_what_was_not_written(self):
        tl = self.t.build_timeline([self.entry(1, "Dolo 650 Tablet", "Tab Dolo 650 1-0-1"), self.entry(2, "X Tablet", "Tab X 0-1-0 x sdays")])
        durations = {i["medicine"]: i["duration"] for s in tl["slots"] for i in s["items"]}
        self.assertEqual(durations["Dolo 650 Tablet"], "duration not written")
        self.assertEqual(durations["X Tablet"], "number of days could not be read")

    def test_a_possible_schedule_is_marked_possible(self):
        tl = self.t.build_timeline([self.entry(1, "Pan-D Capsule PR", "T. pan - D 100", form="Capsule")])
        item = tl["slots"][0]["items"][0]
        self.assertTrue(item["possible"])
        self.assertEqual((tl["slots"][0]["slot"], item["amount"]), ("morning", "1 capsule"))

    def test_lines_that_are_not_identified_are_listed_apart_and_never_by_name(self):
        tl = self.t.build_timeline([self.entry(1, None, "T Lincont 100", identified=False)])
        self.assertEqual(tl["slots"], [])
        self.assertEqual(tl["groups"], [])
        self.assertEqual(tl["not_identified"][0]["source_text"], "T Lincont 100")
        self.assertTrue(tl["not_identified"][0]["possible"])
        self.assertTrue(tl["has_content"])

    def test_frequency_only_as_needed_and_weekly_have_their_own_places(self):
        tl = self.t.build_timeline([
            self.entry(1, "Telma 40 Tablet", "Tab Telma 40 OD"), self.entry(2, "Dolo 650 Tablet", "Tab Dolo 650 SOS"),
            self.entry(3, "D3 60K Capsule", "Cap D3 60K once in a week x 8 weeks", form="Capsule"), self.entry(4, "Ecosprin 75 Tablet", "T. Ecosprin 75 HS"),
        ])
        groups = {g["group"]: [i["medicine"] for i in g["items"]] for g in tl["groups"]}
        self.assertEqual(groups, {"time_not_written": ["Telma 40 Tablet"], "as_needed": ["Dolo 650 Tablet"], "weekly": ["D3 60K Capsule"]})
        self.assertEqual([i["medicine"] for s in tl["slots"] for i in s["items"]], ["Ecosprin 75 Tablet"])     # "at night" is explicit
        weekly = next(g for g in tl["groups"] if g["group"] == "weekly")["items"][0]
        self.assertEqual(weekly["duration"], "for 8 weeks")

    def test_an_empty_or_unreadable_prescription_has_no_timeline(self):
        self.assertFalse(self.t.build_timeline([])["has_content"])
        self.assertFalse(self.t.build_timeline([self.entry(1, "Dolo 650 Tablet", "Tab Dolo 650")])["has_content"])

    def test_the_four_slot_schedule_includes_the_evening(self):
        tl = self.t.build_timeline([self.entry(1, "X Tablet", "Tab X 1-1-1-1")])
        self.assertEqual([s["slot"] for s in tl["slots"]], ["morning", "afternoon", "evening", "night"])


class ThroughTheApiAndPdf(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.client = self.app.test_client()
        self.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        from app.models.prescription_model import save_ocr_result
        from app.routes.prescriptions import _rerun_analysis, _run_medicine_detection
        with self.app.app_context():
            self.uid = self.accounts.user(allergies=[])
            self.pid = self.accounts.prescription(self.uid)
            self.h = {"Authorization": f"Bearer {create_access_token(identity=str(self.uid))}"}
            lines = [{"text": t} for t in ("1. Tab Dolo 650", "1-0-1 x 5 days", "2. Tab Azee 500 1-0-0 for 3 days", "3. T Lincont 100", "x30dys")]
            save_ocr_result(self.pid, "\n".join(l["text"] for l in lines), 0.9, lines=[{**l, "confidence": 0.95, "uncertain": False} for l in lines])
            _run_medicine_detection(self.pid, lines)
            _rerun_analysis(self.pid)

    def tearDown(self):
        with self.app.app_context():
            self.accounts.cleanup()

    def test_the_detail_response_carries_instructions_and_a_timeline(self):
        body = self.client.get(f"/api/prescriptions/{self.pid}", headers=self.h).get_json()
        lines = {m["raw_text"]: m for m in body["detected_medicines"]}
        self.assertEqual(lines["1. Tab Dolo 650"]["instructions"]["duration"], "5 days")
        self.assertEqual(lines["1. Tab Dolo 650"]["instructions"]["schedule"], "1-0-1")
        tl = body["timeline"]
        self.assertTrue(tl["has_content"])
        names = {i["medicine"] for s in tl["slots"] for i in s["items"]}
        self.assertEqual(names, {"Dolo 650 Tablet", "Azee 500 Tablet"})                     # only identified medicines are named
        self.assertEqual(tl["not_identified"][0]["source_text"], "3. T Lincont 100")
        self.assertTrue(tl["not_identified"][0]["possible"])

    def test_the_pdf_uses_the_same_timeline(self):
        from app.models.prescription_model import get_prescription_by_id
        from app.services.smart_report_service import collect_report_data
        with self.app.app_context():
            data = collect_report_data(self.pid, get_prescription_by_id(self.pid))
        api = self.client.get(f"/api/prescriptions/{self.pid}", headers=self.h).get_json()["timeline"]
        self.assertEqual(data["timeline"], api)
        r = self.client.get(f"/api/prescriptions/{self.pid}/report", headers=self.h)
        self.assertEqual((r.status_code, r.mimetype), (200, "application/pdf"))
        self.assertTrue(r.data.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
