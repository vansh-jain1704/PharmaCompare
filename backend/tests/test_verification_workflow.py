"""
The "Needs verification" workflow, end to end:

  upload -> OCR line -> matcher result (settled, or unsettled WITH reasons and look-alike candidates)
  -> person reviews the candidates, confirms one (conflicts are flagged and must be acknowledged) or says
  "not identified" -> decision saved, analysis re-run, original OCR text kept, decision recorded for review.

Nothing here lets a similarity score settle a line: only the person does, and an unsettled line never reaches
the price, recommendation or safety stages.
"""
import json
import unittest

from tests import helpers


def medicine(name):
    from app.db import get_connection
    from app.models.medicine_model import get_medicine_by_id
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT medicine_id FROM Medicines WHERE medicine_name = %s LIMIT 1", (name,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    assert row, f"{name!r} is not in the dataset"
    return get_medicine_by_id(row[0])


def codes(findings, severity=None):
    return {f["code"] for f in findings if severity is None or f["severity"] == severity}


class StatusVocabulary(unittest.TestCase):
    """Which line states may reach the safety, price and recommendation stages. Only a matcher match or a person's confirmation."""

    def test_only_matched_and_user_confirmed_are_settled(self):
        from app.services import match_status as ms
        self.assertTrue(ms.is_confirmed(ms.MATCHED))
        self.assertTrue(ms.is_confirmed(ms.USER_CONFIRMED))
        for status in (ms.NEEDS_VERIFICATION, ms.USER_UNMATCHED, "", None, "anything_else"):
            self.assertFalse(ms.is_confirmed(status), status)
        self.assertEqual(ms.CONFIRMED_STATUSES, frozenset({"matched", "user_confirmed"}))


class ScreenAndPdfRoundTheSameWay(unittest.TestCase):
    """Python rounds .5 to the even number, the screen (Math.round) rounds it up: a 92.5% confidence read 92% in the PDF and 93% on screen."""

    def test_halves_round_up(self):
        from app.services.display_rounding import percent, round_half_up
        self.assertEqual([percent(x) for x in (0.925, 0.935, 0.915, 0.9, 0.8174, 1.0, 0.0)], [93, 94, 92, 90, 82, 100, 0])
        self.assertEqual([round_half_up(x) for x in (55.5, 56.5, 56.4, 0.5, 1.5)], [56, 57, 56, 1, 2])
        self.assertEqual(round(92.5), 92)                      # what plain round() would have said

    def test_the_pdf_words_a_half_percent_confidence_like_the_screen(self):
        from app.services.smart_report_service import _confidence_text
        pm = {"match_status": "matched", "match_confidence": 0.925}
        self.assertEqual(_confidence_text(pm, True), "93% confidence")
        self.assertEqual(_confidence_text({"match_status": "needs_verification", "match_confidence": 0.925}, False), "Closest guess: 93%")

    def test_the_reasons_quote_the_same_percentages_the_screen_shows(self):
        from app.services.medicine_safety_service import annotate
        row = {"pm_id": 1, "raw_text": "x", "match_status": "needs_verification", "match_confidence": None, "match_options": None,
               "medicine_id": None, "primary_salt": None}
        out = annotate([row], [], [{"text": "x", "confidence": 0.625, "uncertain": True}])[1]
        self.assertTrue(any("(63%)" in r for r in out["verification_reasons"]), out["verification_reasons"])


class MatcherReasonsAndGuesses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from app.services.medicine_matching_service import match_line, MAX_OPTIONS
        cls.match_line, cls.MAX_OPTIONS = staticmethod(match_line), MAX_OPTIONS

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def test_a_line_with_only_look_alikes_is_unsettled_and_carries_candidates_with_reasons(self):
        r = self.match_line("T Lincont 100")
        self.assertEqual(r["status"], "needs_verification")
        guesses = r["guesses"]
        self.assertTrue(0 < len(guesses) <= self.MAX_OPTIONS)
        for g in guesses:
            for key in ("medicine_id", "medicine_name", "composition", "form", "strength", "score", "reasons"):
                self.assertIn(key, g)
            self.assertTrue(g["reasons"], "every look-alike says why it was not accepted")
            self.assertIn("only similar", " ".join(g["reasons"]))
        scores = [g["score"] for g in guesses]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(len({g["medicine_id"] for g in guesses}), len(guesses))

    def test_a_similarity_score_alone_never_settles_a_line(self):
        for text in ("T Lincont 100", "T. Linogen . XT", "T shel cal soong 0-1-0", "Tab Zincovit"):
            r = self.match_line(text)
            self.assertEqual(r["status"], "needs_verification", text)
            self.assertNotEqual(r["status"], "matched")

    def test_a_clearly_written_known_medicine_is_still_settled_and_carries_no_guesses(self):
        r = self.match_line("Tab Dolo 650")
        self.assertEqual(r["status"], "matched")
        self.assertEqual(r["medicine"]["medicine_name"], "Dolo 650 Tablet")
        self.assertFalse(r.get("guesses"))

    def test_the_multiplication_sign_ocr_returns_for_x_is_a_course_length_not_a_strength(self):
        # Google Vision writes "x 10 days" as "× 10 days"; the 10 must not be taken for a strength
        plain = self.match_line("4. Tab Zincovit 1-0-0 x 10 days")
        times = self.match_line("4. Tab Zincovit 1-0-0 × 10 days")
        self.assertEqual(times["status"], plain["status"])
        self.assertEqual([g["medicine_id"] for g in times["guesses"]], [g["medicine_id"] for g in plain["guesses"]])
        self.assertEqual(self.match_line("1. Tab Dolo 650 1-0-1 × 5 days")["medicine"]["medicine_name"], "Dolo 650 Tablet")

    def test_the_word_for_in_a_course_length_is_not_a_brand_to_look_up(self):
        # "for 30 days" used to look up brands starting "For..." and offer "Forlevo Tablet" as a look-alike
        r = self.match_line("5. Tab Shelcal 500 0-1-0 for 30 days")
        self.assertEqual(r["status"], "needs_verification")
        self.assertIsNone(r["medicine"])
        self.assertFalse(r.get("guesses"))
        self.assertEqual(self.match_line("1. Tab Dolo 650 1-0-1 for 5 days")["medicine"]["medicine_name"], "Dolo 650 Tablet")

    def test_text_that_resembles_nothing_has_no_candidates(self):
        r = self.match_line("2TTE 2016 OTG")
        self.assertEqual(r["status"], "needs_verification")
        self.assertIsNone(r["medicine"])
        self.assertFalse(r.get("guesses"))


class AssessConfirmation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from app.services.medicine_matching_service import assess_confirmation
        cls.assess = staticmethod(assess_confirmation)

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def test_the_zincold_case_is_flagged_on_name_form_and_number(self):
        findings = self.assess("T Lincont 100", medicine("Zincold Syrup"))
        self.assertEqual(codes(findings, "conflict"), {"name", "form", "number"})
        text = " ".join(f["text"] for f in findings)
        self.assertIn("tablet", text)
        self.assertIn("syrup", text)
        self.assertIn("1-0-0", text)             # the schedule-misread explanation for the "100"

    def test_a_clear_match_has_nothing_to_flag(self):
        self.assertEqual(self.assess("Tab Dolo 650", medicine("Dolo 650 Tablet")), [])

    def test_a_different_strength_is_a_conflict(self):
        self.assertIn("number", codes(self.assess("Tab Dolo 650", medicine("Dolo 500 Tablet")), "conflict"))
        self.assertIn("strength", codes(self.assess("Dolo 650mg", medicine("Dolo 500 Tablet")), "conflict"))

    def test_a_written_form_the_product_lacks_is_a_conflict(self):
        findings = self.assess("Tab Dolo 650", medicine("Dolo 120 Suspension"))
        self.assertIn("form", codes(findings, "conflict"))

    def test_a_stated_release_type_the_product_lacks_is_a_conflict(self):
        self.assertIn("release", codes(self.assess("Metformin 500 SR", medicine("DavaIndia Metformin 500mg Tablet")), "conflict"))

    def test_an_ingredient_the_line_names_but_the_product_lacks_is_a_conflict(self):
        from app.db import get_connection
        from app.models.medicine_model import get_medicine_by_id
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT medicine_id FROM Medicines WHERE composition = 'Amoxycillin (500mg)' AND form = 'Capsule' LIMIT 1")
        plain = get_medicine_by_id(cur.fetchone()[0])
        cur.close()
        conn.close()
        self.assertIn("ingredient", codes(self.assess("Amoxicillin 500 + Clavulanic acid 125", plain), "conflict"))

    def test_text_that_carries_nothing_to_compare_produces_no_findings(self):
        for text in ("Added manually", "", None, "x 5 days"):
            self.assertEqual(self.assess(text, medicine("Dolo 650 Tablet")), [])

    def test_facts_about_the_chosen_product_are_notes_not_conflicts(self):
        from app.db import get_connection
        from app.models.medicine_model import get_medicine_by_id
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT medicine_id FROM Medicines WHERE is_discontinued = 1 LIMIT 1")
        old = get_medicine_by_id(cur.fetchone()[0])
        cur.close()
        conn.close()
        findings = self.assess(old["medicine_name"], old)
        self.assertEqual(codes(findings, "conflict"), set())
        self.assertIn("discontinued", codes(findings, "note"))

    def test_a_schedule_lookalike_number_is_explained_but_a_real_strength_mismatch_is_not(self):
        self.assertIn("1-0-0", " ".join(f["text"] for f in self.assess("Tab Dolo 100", medicine("Dolo 650 Tablet"))))
        self.assertNotIn("1-0-0", " ".join(f["text"] for f in self.assess("Tab Dolo 500", medicine("Dolo 650 Tablet"))))


class WorkflowThroughTheApi(unittest.TestCase):
    """The real routes, the real database, throw-away accounts that are removed again."""

    def setUp(self):
        self.app = helpers.get_app()
        self.client = self.app.test_client()
        self.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        from app.services.medicine_matching_service import match_line
        with self.app.app_context():
            self.uid = self.accounts.user(allergies=[])
            self.other = self.accounts.user(allergies=[])
            self.pid = self.accounts.prescription(self.uid)
            self.other_pid = self.accounts.prescription(self.other)
            self.h = {"Authorization": f"Bearer {create_access_token(identity=str(self.uid))}"}
            self.h_other = {"Authorization": f"Bearer {create_access_token(identity=str(self.other))}"}
            guesses = match_line("T Lincont 100")["guesses"]
            self.guess_names = [g["medicine_name"] for g in guesses]
            store = {"kind": "closest_guesses", "candidates": guesses}
            # a line the matcher could only match to look-alikes, as detection stores it
            self.pm = self.accounts.line(self.pid, None, raw_text="T Lincont 100", status="needs_verification",
                                         confidence=0.8174, match_options=store)
            self.pm_clean = self.accounts.line(self.pid, None, raw_text="Tab Dolo 650", status="needs_verification", confidence=0.8)
            self.pm_other = self.accounts.line(self.other_pid, None, raw_text="y", status="needs_verification", confidence=0.5)
            self.dolo = medicine("Dolo 650 Tablet")["medicine_id"]
            self.zincold = medicine("Zincold Syrup")["medicine_id"]
            self.log_rows_before = self.log_count()

    def tearDown(self):
        with self.app.app_context():
            self.accounts.cleanup()
        # nothing the test recorded may outlive it: the trail goes with the prescription it belongs to
        self.assertEqual(self.log_count(), self.log_rows_before)

    # ---- helpers -------------------------------------------------------------------------
    def log_count(self):
        from app.db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM System_Logs WHERE action = 'medicine_verification'")
        value = cur.fetchone()[0]
        cur.close()
        conn.close()
        return value

    def pm_row(self, pm_id):
        from app.db import get_connection
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM Prescription_Medicines WHERE pm_id = %s", (pm_id,))
        value = cur.fetchone()
        cur.close()
        conn.close()
        return value

    def price_rows(self, pm_id):
        from app.db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM Price_Comparison WHERE pm_id = %s", (pm_id,))
        value = cur.fetchone()[0]
        cur.close()
        conn.close()
        return value

    def patch(self, pm, body, pid=None, headers=None):
        return self.client.patch(f"/api/prescriptions/{pid or self.pid}/medicines/{pm}", json=body, headers=headers or self.h)

    def unmatch(self, pm, pid=None, headers=None):
        return self.client.post(f"/api/prescriptions/{pid or self.pid}/medicines/{pm}/unmatched", headers=headers or self.h)

    def detail(self):
        return self.client.get(f"/api/prescriptions/{self.pid}", headers=self.h).get_json()

    def log(self, headers=None, pid=None):
        return self.client.get(f"/api/prescriptions/{pid or self.pid}/verification-log", headers=headers or self.h)

    # ---- what the person sees before deciding ---------------------------------------------
    def test_an_unsettled_line_shows_its_reasons_and_look_alikes_and_is_not_settled(self):
        line = next(d for d in self.detail()["detected_medicines"] if d["pm_id"] == self.pm)
        self.assertEqual(line["match_status"], "needs_verification")
        self.assertIsNone(line["medicine_id"])
        self.assertEqual(line["raw_text"], "T Lincont 100")
        self.assertEqual([g["medicine_name"] for g in line["closest_guesses"]], self.guess_names)
        self.assertTrue(line["verification_reasons"])
        self.assertIn("only similar", " ".join(line["verification_reasons"]))
        self.assertIn("look-alike", line["verification_label"])
        self.assertFalse(line["needs_disambiguation"])         # look-alikes are not a "choose between" list
        self.assertEqual(line["match_options"], [])
        self.assertIsNone(line["verification_decision"])

    def test_a_line_with_no_candidates_says_why(self):
        pm = self.accounts.line(self.pid, None, raw_text="2TTE 2016 OTG", status="needs_verification", confidence=None)
        line = next(d for d in self.detail()["detected_medicines"] if d["pm_id"] == pm)
        self.assertEqual(line["closest_guesses"], [])
        self.assertIn("No product on file resembles this text", " ".join(line["verification_reasons"]))

    def test_unsettled_lines_never_reach_price_or_recommendations(self):
        body = self.detail()
        self.assertEqual(body["price_comparison"], [])
        self.assertEqual(body["recommendations"], [])
        self.assertEqual(self.price_rows(self.pm), 0)

    # ---- confirming ------------------------------------------------------------------------
    def test_a_conflicting_choice_is_held_with_plain_warnings_and_nothing_is_saved(self):
        before = self.log_count()
        r = self.patch(self.pm, {"medicine_id": self.zincold})
        self.assertEqual(r.status_code, 409)
        body = r.get_json()
        self.assertEqual(body["error"], "confirmation_needs_acknowledgement")
        self.assertEqual(codes(body["warnings"], "conflict"), {"name", "form", "number"})
        self.assertIn("medically equivalent", body["message"])
        row = self.pm_row(self.pm)
        self.assertEqual((row["match_status"], row["medicine_id"]), ("needs_verification", None))
        self.assertIsNotNone(row["match_options"])             # the candidates are untouched
        self.assertEqual(self.price_rows(self.pm), 0)
        self.assertEqual(self.log_count(), before)             # a refused attempt is not a decision

    def test_only_an_explicit_true_acknowledges(self):
        for value in ("true", 1, "yes", None, False, [True]):
            r = self.patch(self.pm, {"medicine_id": self.zincold, "acknowledge_warnings": value})
            self.assertEqual(r.status_code, 409, value)
        self.assertEqual(self.pm_row(self.pm)["match_status"], "needs_verification")

    def test_an_acknowledged_choice_is_saved_as_confirmed_by_you_and_recorded_with_what_they_saw(self):
        r = self.patch(self.pm, {"medicine_id": self.zincold, "acknowledge_warnings": True})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["warnings_acknowledged"])
        self.assertTrue(body["audit_logged"])
        row = self.pm_row(self.pm)
        self.assertEqual((row["match_status"], row["medicine_id"]), ("user_confirmed", self.zincold))
        self.assertEqual(row["raw_text"], "T Lincont 100")      # the OCR text is kept exactly as read
        # the analysis now exists for this line (the wrong-product risk is exactly why it was flagged first)
        self.assertGreater(self.price_rows(self.pm), 0)

        log = self.log().get_json()
        self.assertEqual(log["count"], 1)
        d = log["decisions"][0]
        self.assertEqual((d["decision"], d["pm_id"], d["medicine_id"], d["medicine_name"]), ("confirmed", self.pm, self.zincold, "Zincold Syrup"))
        self.assertEqual((d["raw_text"], d["previous_status"], d["warnings_acknowledged"]), ("T Lincont 100", "needs_verification", True))
        self.assertAlmostEqual(d["previous_confidence"], 0.8174, places=4)
        self.assertEqual([s["medicine_name"] for s in d["suggestions"]], self.guess_names)   # what they were shown
        self.assertEqual(codes(d["warnings"], "conflict"), {"name", "form", "number"})
        self.assertTrue(d["decided_at"])

        line = next(x for x in self.detail()["detected_medicines"] if x["pm_id"] == self.pm)
        self.assertEqual(line["verification_status"], "verified_by_user")
        self.assertEqual(line["verification_decision"]["decision"], "confirmed")
        self.assertTrue(line["verification_decision"]["warnings_acknowledged"])

    def test_a_choice_with_no_conflict_needs_no_acknowledgement(self):
        r = self.patch(self.pm_clean, {"medicine_id": self.dolo})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["warnings_acknowledged"])
        d = self.log().get_json()["decisions"][-1]
        self.assertEqual((d["decision"], d["warnings_acknowledged"], d["warnings"]), ("confirmed", False, []))
        self.assertGreater(self.price_rows(self.pm_clean), 0)

    def test_confirming_a_line_refreshes_its_price_comparison_and_only_its_own(self):
        self.assertEqual(self.price_rows(self.pm), 0)
        self.patch(self.pm_clean, {"medicine_id": self.dolo})
        self.assertGreater(self.price_rows(self.pm_clean), 0)
        self.assertEqual(self.price_rows(self.pm), 0)           # the other, still unsettled line stays out
        prices = self.detail()["price_comparison"]
        self.assertEqual({p["pm_id"] for p in prices}, {self.pm_clean})

    def test_a_line_cannot_be_confirmed_by_or_for_someone_else(self):
        self.assertEqual(self.patch(self.pm, {"medicine_id": self.dolo, "acknowledge_warnings": True}, headers=self.h_other).status_code, 404)
        self.assertEqual(self.patch(self.pm_other, {"medicine_id": self.dolo, "acknowledge_warnings": True}).status_code, 404)
        self.assertEqual(self.patch(self.pm, {"medicine_id": self.dolo}, pid=self.other_pid, headers=self.h_other).status_code, 404)
        self.assertEqual(self.log_count(), self.log_rows_before)

    # ---- not identified --------------------------------------------------------------------
    def test_a_line_can_be_marked_not_identified_and_keeps_everything_it_was_shown(self):
        r = self.unmatch(self.pm)
        self.assertEqual(r.status_code, 200)
        row = self.pm_row(self.pm)
        self.assertEqual((row["match_status"], row["medicine_id"]), ("user_unmatched", None))
        self.assertEqual(row["raw_text"], "T Lincont 100")
        self.assertAlmostEqual(float(row["match_confidence"]), 0.8174, places=4)
        self.assertIn("closest_guesses", row["match_options"])  # the candidates are kept for review
        self.assertEqual(self.price_rows(self.pm), 0)

        line = next(x for x in self.detail()["detected_medicines"] if x["pm_id"] == self.pm)
        self.assertEqual(line["verification_status"], "marked_unidentified")
        self.assertIn("not included in the safety, price or savings", line["verification_label"])
        self.assertTrue(line["user_unmatched"])
        self.assertEqual(line["verification_decision"]["decision"], "unmatched")
        d = self.log().get_json()["decisions"][-1]
        self.assertEqual((d["decision"], d["medicine_id"], d["previous_status"]), ("unmatched", None, "needs_verification"))

    def test_marking_a_confirmed_line_not_identified_removes_what_was_derived_from_it(self):
        self.patch(self.pm_clean, {"medicine_id": self.dolo})
        self.assertGreater(self.price_rows(self.pm_clean), 0)
        self.assertEqual(self.unmatch(self.pm_clean).status_code, 200)
        self.assertEqual(self.price_rows(self.pm_clean), 0)
        self.assertEqual(self.detail()["price_comparison"], [])
        self.assertEqual([d["decision"] for d in self.log().get_json()["decisions"]], ["confirmed", "unmatched"])

    def test_a_not_identified_line_can_be_reopened_and_confirmed_later(self):
        self.unmatch(self.pm_clean)
        r = self.patch(self.pm_clean, {"medicine_id": self.dolo})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.pm_row(self.pm_clean)["match_status"], "user_confirmed")
        self.assertEqual([d["decision"] for d in self.log().get_json()["decisions"]], ["unmatched", "confirmed"])

    def test_marking_not_identified_is_owner_only_and_needs_a_login(self):
        self.assertEqual(self.unmatch(self.pm, headers=self.h_other).status_code, 404)
        self.assertEqual(self.unmatch(self.pm_other).status_code, 404)
        self.assertEqual(self.client.post(f"/api/prescriptions/{self.pid}/medicines/{self.pm}/unmatched").status_code, 401)
        self.assertEqual(self.pm_row(self.pm)["match_status"], "needs_verification")

    # ---- the review trail --------------------------------------------------------------------
    def test_the_trail_is_private_ordered_and_removed_with_its_prescription(self):
        self.assertEqual(self.log(headers=self.h_other).status_code, 404)
        self.assertEqual(self.client.get(f"/api/prescriptions/{self.pid}/verification-log").status_code, 401)
        self.assertEqual(self.log().get_json()["decisions"], [])
        self.patch(self.pm_clean, {"medicine_id": self.dolo})
        self.unmatch(self.pm)
        decisions = self.log().get_json()["decisions"]
        self.assertEqual([d["decision"] for d in decisions], ["confirmed", "unmatched"])
        self.assertEqual([d["pm_id"] for d in decisions], [self.pm_clean, self.pm])
        # another prescription's trail is separate
        other_decisions = self.log(headers=self.h_other, pid=self.other_pid).get_json()["decisions"]
        self.assertEqual(other_decisions, [])
        # deleting the prescription takes its trail with it
        self.assertEqual(self.client.delete(f"/api/prescriptions/{self.pid}", headers=self.h).status_code, 200)
        self.assertEqual(self.log_count(), self.log_rows_before)

    def test_adding_a_medicine_by_hand_is_recorded_too(self):
        r = self.client.post(f"/api/prescriptions/{self.pid}/medicines", json={"medicine_id": self.dolo}, headers=self.h)
        self.assertEqual(r.status_code, 201)
        d = self.log().get_json()["decisions"][-1]
        self.assertEqual((d["decision"], d["medicine_id"], d["raw_text"]), ("added_manually", self.dolo, "Added manually"))

    # ---- picker honesty ------------------------------------------------------------------------
    def test_look_alike_search_results_are_labelled_as_different_medicines(self):
        r = self.client.get("/api/medicines/search?q=zincovit", headers=self.h).get_json()
        self.assertTrue(r["fallback"])
        self.assertIn("different medicines", r["fallback_note"])
        self.assertTrue(r["medicines"])
        direct = self.client.get("/api/medicines/search?q=Dolo 650", headers=self.h).get_json()
        self.assertFalse(direct["fallback"])
        self.assertIsNone(direct["fallback_note"])


class FormConflictAndReport(unittest.TestCase):
    """A matched line whose written form differs from the product is flagged; the PDF words every state like the screen."""

    def setUp(self):
        self.app = helpers.get_app()
        self.client = self.app.test_client()
        self.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        with self.app.app_context():
            self.uid = self.accounts.user(allergies=[])
            self.pid = self.accounts.prescription(self.uid)
            self.h = {"Authorization": f"Bearer {create_access_token(identity=str(self.uid))}"}
            self.capsule_vs_tablet = self.accounts.line(self.pid, "Omez FF 20 Tablet", raw_text="Cap Omez 20 1-0-0", status="matched", confidence=0.7441)
            self.clean = self.accounts.line(self.pid, "Dolo 650 Tablet", raw_text="Tab Dolo 650", status="matched", confidence=1.0)
            self.confirmed = self.accounts.line(self.pid, "Omez FF 20 Tablet", raw_text="Cap Omez 20", status="user_confirmed", confidence=None)
            self.unmatched = self.accounts.line(self.pid, None, raw_text="T Lincont 100", status="user_unmatched", confidence=0.8174)
            self.unsettled = self.accounts.line(self.pid, None, raw_text="2TTE 2016 OTG", status="needs_verification", confidence=None)

    def tearDown(self):
        with self.app.app_context():
            self.accounts.cleanup()

    def lines(self):
        return {d["pm_id"]: d for d in self.client.get(f"/api/prescriptions/{self.pid}", headers=self.h).get_json()["detected_medicines"]}

    def test_an_automatic_match_with_a_different_form_is_flagged_but_still_the_matchers_decision(self):
        flagged = self.lines()[self.capsule_vs_tablet]
        self.assertEqual(flagged["match_status"], "matched")                      # not changed
        self.assertTrue(flagged["form_conflict"])
        self.assertEqual(flagged["verification_status"], "flagged_for_review")
        self.assertIn("capsule", flagged["verification_label"])
        self.assertIn("tablet", flagged["verification_label"])

    def test_no_flag_when_the_form_agrees_or_the_person_has_decided(self):
        lines = self.lines()
        self.assertFalse(lines[self.clean]["form_conflict"])
        self.assertFalse(lines[self.confirmed]["form_conflict"])                  # their decision settles it
        self.assertEqual(lines[self.confirmed]["verification_status"], "verified_by_user")
        self.assertFalse(lines[self.unmatched]["form_conflict"])

    def test_the_pdf_uses_the_same_words_and_savings_rule_as_the_screen(self):
        from app.models.prescription_model import get_prescription_by_id
        from app.routes.prescriptions import _rerun_analysis
        from app.services.smart_report_service import collect_report_data
        with self.app.app_context():
            _rerun_analysis(self.pid)                  # the analysis the app runs after any change
            data = collect_report_data(self.pid, get_prescription_by_id(self.pid))
        status = {ln["pm"]["pm_id"]: ln["status"] for ln in data["lines"]}
        self.assertEqual(status[self.capsule_vs_tablet], "Check match")
        self.assertEqual(status[self.clean], "Matched")
        self.assertEqual(status[self.confirmed], "Confirmed")
        self.assertEqual(status[self.unmatched], "Not identified (by you)")
        self.assertEqual(status[self.unsettled], "Needs verification")
        confidence = {ln["pm"]["pm_id"]: ln["confidence"] for ln in data["lines"]}
        self.assertEqual(confidence[self.unmatched], "Marked by you")
        # a line waiting on a check, and lines that are not identified, never add to the savings total
        reasons = {ln["pm"]["pm_id"]: ln["reason"] for ln in data["lines"]}
        self.assertEqual(reasons[self.unmatched], "Not identified")
        self.assertEqual(reasons[self.unsettled], "Not identified")
        self.assertEqual(reasons[self.capsule_vs_tablet], "Not counted: check match first")   # priced, with cheaper options, yet not counted
        counted = [ln["pm"]["pm_id"] for ln in data["lines"] if ln["saving"]]
        self.assertNotIn(self.capsule_vs_tablet, counted)
        self.assertNotIn(self.unmatched, counted)
        self.assertNotIn(self.unsettled, counted)
        self.assertEqual(data["counted_for_savings"], len(counted))
        # "settled" means identified and not waiting on a check: the not-identified line is decided but not settled
        self.assertEqual(data["settled"], 2)                                       # Dolo (matched) and the confirmed Omez
        self.assertEqual(data["needs_attention"], 2)                               # the flagged capsule line and the unsettled one

    def test_the_report_downloads_with_every_kind_of_line_present(self):
        r = self.client.get(f"/api/prescriptions/{self.pid}/report", headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/pdf")
        self.assertTrue(r.data.startswith(b"%PDF"))


class ConfirmedDespiteConflicts(unittest.TestCase):
    """A person's confirmation stands, but a saving that rests on a product that conflicts with the line is never counted."""

    def setUp(self):
        self.app = helpers.get_app()
        self.client = self.app.test_client()
        self.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        with self.app.app_context():
            self.uid = self.accounts.user(allergies=[])
            self.pid = self.accounts.prescription(self.uid)
            self.h = {"Authorization": f"Bearer {create_access_token(identity=str(self.uid))}"}
            self.wrong = self.accounts.line(self.pid, None, raw_text="T Lincont 100", status="needs_verification", confidence=0.8174)
            self.right = self.accounts.line(self.pid, None, raw_text="Tab Dolo 650", status="needs_verification", confidence=0.8)
        self.zincold = medicine("Zincold Syrup")["medicine_id"]
        self.dolo = medicine("Dolo 650 Tablet")["medicine_id"]

    def tearDown(self):
        with self.app.app_context():
            self.accounts.cleanup()

    def confirm(self, pm, medicine_id, ack=False):
        body = {"medicine_id": medicine_id, **({"acknowledge_warnings": True} if ack else {})}
        return self.client.patch(f"/api/prescriptions/{self.pid}/medicines/{pm}", json=body, headers=self.h)

    def lines(self):
        return {d["pm_id"]: d for d in self.client.get(f"/api/prescriptions/{self.pid}", headers=self.h).get_json()["detected_medicines"]}

    def report(self):
        from app.models.prescription_model import get_prescription_by_id
        from app.services.smart_report_service import collect_report_data
        with self.app.app_context():
            return collect_report_data(self.pid, get_prescription_by_id(self.pid))

    def test_a_confirmation_that_conflicts_is_kept_but_marked_and_explained(self):
        self.assertEqual(self.confirm(self.wrong, self.zincold, ack=True).status_code, 200)
        line = self.lines()[self.wrong]
        self.assertEqual(line["match_status"], "user_confirmed")               # the decision stands
        self.assertEqual(line["verification_status"], "verified_by_user")
        self.assertTrue(line["confirmed_with_conflicts"])
        self.assertIn("although it differs from the prescription line", line["verification_label"])
        joined = " ".join(line["confirmation_conflicts"])
        self.assertIn("tablet", joined)
        self.assertIn("syrup", joined)

    def test_its_saving_is_not_counted_on_the_pdf_while_a_clean_confirmation_is(self):
        self.confirm(self.wrong, self.zincold, ack=True)
        self.confirm(self.right, self.dolo)
        data = self.report()
        by_pm = {ln["pm"]["pm_id"]: ln for ln in data["lines"]}
        self.assertEqual(by_pm[self.wrong]["status"], "Confirmed")
        self.assertIsNone(by_pm[self.wrong]["saving"])
        self.assertEqual(by_pm[self.wrong]["reason"], "Not counted: confirmed despite differences from the line")
        self.assertIsNotNone(by_pm[self.right]["saving"])                       # no conflict: counted as before
        self.assertEqual(data["counted_for_savings"], 1)
        self.assertEqual(round(data["total_saving"], 2), round(by_pm[self.right]["saving"], 2))

    def test_a_clean_confirmation_and_a_hand_added_medicine_carry_no_conflict(self):
        self.confirm(self.right, self.dolo)
        added = self.client.post(f"/api/prescriptions/{self.pid}/medicines", json={"medicine_id": self.zincold}, headers=self.h).get_json()["pm_id"]
        lines = self.lines()
        self.assertFalse(lines[self.right]["confirmed_with_conflicts"])
        self.assertFalse(lines[added]["confirmed_with_conflicts"])              # nothing was written to contradict
        self.assertEqual(lines[self.right]["verification_label"], "Confirmed by you")

    def test_every_decision_on_a_line_is_kept_in_order(self):
        self.confirm(self.wrong, self.zincold, ack=True)
        self.client.post(f"/api/prescriptions/{self.pid}/medicines/{self.wrong}/unmatched", headers=self.h)
        self.confirm(self.wrong, self.dolo, ack=True)
        line = self.lines()[self.wrong]
        self.assertEqual([d["decision"] for d in line["verification_history"]], ["confirmed", "unmatched", "confirmed"])
        self.assertEqual([d["medicine_name"] for d in line["verification_history"]], ["Zincold Syrup", None, "Dolo 650 Tablet"])
        self.assertEqual(line["verification_decision"], line["verification_history"][-1])
        self.assertEqual(self.lines()[self.right]["verification_history"], [])


class DetectionStoresWhatTheMatcherFound(unittest.TestCase):
    """_run_medicine_detection: a settled line stores a product, an unsettled one stores only look-alikes."""

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

    def test_stored_guesses_are_candidates_only_and_the_line_points_at_no_product(self):
        from app.routes.prescriptions import _run_medicine_detection
        from app.models.medicine_model import get_prescription_medicine
        detected = _run_medicine_detection(self.pid, [{"text": "Tab Dolo 650"}, {"text": "T Lincont 100"}, {"text": "2TTE 2016 OTG"}])
        by_text = {d["raw_text"]: d for d in detected}
        settled, unsettled, nothing = by_text["Tab Dolo 650"], by_text["T Lincont 100"], by_text["2TTE 2016 OTG"]

        self.assertEqual(settled["status"], "matched")
        self.assertIsNone(get_prescription_medicine(settled["pm_id"])["match_options"])

        self.assertEqual(unsettled["status"], "needs_verification")
        row = get_prescription_medicine(unsettled["pm_id"])
        self.assertIsNone(row["medicine_id"])
        stored = json.loads(row["match_options"])
        self.assertEqual(stored["kind"], "closest_guesses")
        self.assertTrue(stored["candidates"])
        self.assertTrue(all(c["reasons"] for c in stored["candidates"]))

        row = get_prescription_medicine(nothing["pm_id"])
        self.assertEqual((row["match_status"], row["medicine_id"], row["match_options"]), ("needs_verification", None, None))


if __name__ == "__main__":
    unittest.main()
