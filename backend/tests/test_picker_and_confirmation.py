"""
The manual verification flow: the picker's search (parsing, normalisation, relevance ranking, what it returns), and the
routes that save what the person chose (confirm a line, add a medicine, remove a line).

Nothing here may confirm a medicine on a similarity score: a line stays unconfirmed until the person confirms a product,
and searching never changes any data.
"""
import time
import unittest

from tests import helpers


def row(medicine_id, name, composition="Alpha (10mg)", form="Tablet", strength="10mg", release_type=None,
        is_discontinued=0, composition_incomplete=0):
    return {"medicine_id": medicine_id, "medicine_name": name, "composition": composition, "form": form, "strength": strength,
            "release_type": release_type, "is_discontinued": is_discontinued, "composition_incomplete": composition_incomplete}


class QueryParsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.services import medicine_search
        cls.s = medicine_search

    def test_hyphens_dots_spaces_and_case_are_all_the_same_query(self):
        for q in ("Pan D", "pan-d", "pan - D", "PAN  D", "Pan.D", " pan   -d "):
            self.assertEqual(self.s.parse_query(q)["tokens"], ["pan", "d"], q)

    def test_a_leading_T_or_Tab_is_a_form_hint_not_a_word_to_find(self):
        for q in ("T. pan - D", "T pan-D", "Tab Pan D", "pan d tablet"):
            parsed = self.s.parse_query(q)
            self.assertEqual((parsed["tokens"], parsed["form_hint"]), (["pan", "d"], "tablet"), q)
        self.assertEqual(self.s.parse_query("Cap D3 60K")["form_hint"], "capsule")
        self.assertEqual(self.s.parse_query("Dolo 650")["form_hint"], None)

    def test_strengths_are_glued_to_their_units(self):
        self.assertEqual(self.s.parse_query("60 K capsule")["tokens"], ["60k"])
        self.assertEqual(self.s.parse_query("Metformin 500 mg")["tokens"], ["metformin", "500mg"])
        self.assertEqual(self.s.parse_query("vitamin d3 60,000")["tokens"], ["vitamin", "d3", "60000"])
        self.assertEqual(self.s.parse_query("Telmisartan 2.5")["tokens"], ["telmisartan", "2.5"])

    def test_release_words_are_recognised_but_mr_is_just_a_word(self):
        self.assertEqual(self.s.parse_query("Metformin 500 SR")["release_hints"], {"sr": "sr"})
        self.assertEqual(self.s.parse_query("nifedipine 20 retard")["release_hints"], {"retard": "sr"})
        self.assertEqual(self.s.parse_query("aceclofenac MR")["release_hints"], {})   # muscle relaxant in most brand names

    def test_a_query_of_only_form_words_searches_for_nothing(self):
        self.assertEqual(self.s.parse_query("tablet")["tokens"], [])
        self.assertEqual(self.s.rank_rows("tablet", [row(1, "Dolo 650 Tablet")]), [])
        self.assertEqual(self.s.rank_rows("", [row(1, "Dolo 650 Tablet")]), [])


class Ranking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.services import medicine_search
        cls.s = medicine_search

    def names(self, term, rows, limit=20):
        return [r["medicine_name"] for r in self.s.rank_rows(term, rows, limit)]

    def test_the_brand_typed_beats_its_look_alikes(self):
        rows = [row(1, "Span D Tablet"), row(2, "Pany D Tablet"), row(3, "Pan-D Capsule PR", form="Capsule", release_type="pr"), row(4, "H-Pan D Tablet"), row(5, "Pandex Tablet")]
        for q in ("Pan D", "pan-d", "pan - D", "T. pan - D"):
            ranked = self.names(q, rows)
            self.assertEqual(ranked[0], "Pan-D Capsule PR", q)
            self.assertNotIn("Pandex Tablet", ranked)       # no whole word "d": a one-letter word is never matched inside another word
            self.assertNotIn("Span D Tablet", ranked[:1])

    def test_whole_words_beat_prefixes_beat_substrings(self):
        rows = [row(1, "Xcalciumx Tablet", composition="Other (1mg)"), row(2, "Calcium Tablet", composition="Other (1mg)"), row(3, "Calciumet Tablet", composition="Other (1mg)")]
        self.assertEqual(self.names("calcium", rows), ["Calcium Tablet", "Calciumet Tablet", "Xcalciumx Tablet"])

    def test_short_words_match_only_at_the_start_of_a_word_never_inside_one(self):
        rows = [row(1, "Calpol Tablet", composition="Other (1mg)"), row(2, "Xcalx Tablet", composition="Other (1mg)"), row(3, "Dolocal Tablet", composition="Other (1mg)")]
        self.assertEqual(self.names("cal", rows), ["Calpol Tablet"])           # 3 letters: whole word or word start only
        self.assertEqual(set(self.names("calp", rows)), {"Calpol Tablet"})
        self.assertEqual(set(self.names("xcal", rows)), {"Xcalx Tablet"})
        self.assertEqual(set(self.names("olocal", rows)), {"Dolocal Tablet"})  # 4+ letters may match inside a word

    def test_a_number_is_a_strength_never_part_of_one(self):
        rows = [row(1, "Amlokind 5 Tablet", composition="Amlodipine (5mg)"), row(2, "Metformin 500mg Tablet", composition="Metformin (500mg)"), row(3, "Foo 50 Tablet", composition="Foo (50mg)")]
        self.assertEqual(self.names("5", rows), ["Amlokind 5 Tablet"])
        self.assertEqual(self.names("500", rows), ["Metformin 500mg Tablet"])
        self.assertEqual(self.names("500mg", rows), ["Metformin 500mg Tablet"])

    def test_60k_means_sixty_thousand_in_the_ingredients(self):
        rows = [row(1, "Hi-D3 60K Capsule", composition="Vitamin D3 (60000IU)", form="Capsule"), row(2, "Loy D3 Capsule", composition="Vitamin D3 (60000IU)", form="Capsule"),
                row(3, "Dr. D3 Injection", composition="Vitamin D3 (600000IU/ml)", form="Injection"), row(4, "D3 Plain Tablet", composition="Vitamin D3 (1000IU)")]
        got = self.names("D3 60K capsule", rows)
        self.assertEqual(set(got), {"Hi-D3 60K Capsule", "Loy D3 Capsule"})
        self.assertEqual(got[0], "Hi-D3 60K Capsule")        # 60K is in its name too
        self.assertEqual(set(self.names("vitamin d3 60,000", rows)), {"Hi-D3 60K Capsule", "Loy D3 Capsule"})

    def test_ingredients_are_searchable_and_every_word_must_match(self):
        rows = [row(1, "Shelc Tablet", composition="Calcium Carbonate (500mg) + Vitamin D3 (250IU)"), row(2, "Calx Tablet", composition="Calcium Carbonate (500mg)"),
                row(3, "Vitd Tablet", composition="Vitamin D3 (1000IU)")]
        self.assertEqual(self.names("calcium carbonate vitamin d3", rows), ["Shelc Tablet"])
        self.assertEqual(set(self.names("calcium", rows)), {"Shelc Tablet", "Calx Tablet"})

    def test_a_release_marker_means_that_release_type(self):
        rows = [row(1, "Metform 500mg Tablet", composition="Metformin (500mg)"), row(2, "Metform 500mg Tablet SR", composition="Metformin (500mg)", release_type="sr"),
                row(3, "Glycomet 500 XR", composition="Metformin (500mg)", release_type="er")]
        self.assertEqual(self.names("Metformin 500 SR", rows), ["Metform 500mg Tablet SR"])     # the plain tablet and the XR are not "SR"
        self.assertEqual(self.names("Metformin 500 XR", rows), ["Glycomet 500 XR"])
        self.assertEqual(self.names("Metformin 500", rows)[0], "Metform 500mg Tablet")          # nothing said: the ordinary product first
        self.assertEqual(len(self.names("Metformin 500", rows)), 3)                              # but the modified-release ones are still listed

    def test_a_single_ingredient_query_prefers_the_single_ingredient_product(self):
        # same-length names that both carry "500": only the combination penalty (not the name score or the tie-break) can order them
        rows = [row(1, "Glim 500 Tablet", composition="Glimepiride (1mg) + Metformin (500mg)"), row(2, "Metx 500 Tablet", composition="Metformin (500mg)")]
        self.assertEqual(self.names("Metformin 500", rows), ["Metx 500 Tablet", "Glim 500 Tablet"])
        # asking for both ingredients removes the preference
        self.assertEqual(self.names("Glimepiride Metformin 500", rows), ["Glim 500 Tablet"])

    def test_the_form_hint_boosts_but_never_excludes(self):
        rows = [row(1, "Dolo 650 Syrup", form="Syrup"), row(2, "Dolo 650 Tablet", form="Tablet")]
        self.assertEqual(self.names("Dolo 650 tablet", rows), ["Dolo 650 Tablet", "Dolo 650 Syrup"])
        self.assertEqual(self.names("T. Dolo 650", rows)[0], "Dolo 650 Tablet")

    def test_discontinued_products_are_listed_but_never_first(self):
        rows = [row(1, "Dolo 650 Tablet", is_discontinued=1), row(2, "Dolopar 650 Tablet"), row(3, "Dololife 650 Tablet")]
        ranked = self.names("Dolo 650", rows)
        self.assertEqual(ranked[-1], "Dolo 650 Tablet")
        self.assertEqual(len(ranked), 3)

    def test_an_incomplete_ingredient_list_ranks_lower(self):
        # same-length names, so only the penalty (not the alphabetical tie-break) can put the complete one first
        rows = [row(1, "Acim 100 Aaa", composition_incomplete=1, composition="Alpha (100mg)"), row(2, "Acim 100 Bbb", composition="Alpha (100mg)")]
        self.assertEqual(self.names("acim 100", rows), ["Acim 100 Bbb", "Acim 100 Aaa"])
        rows[0]["composition_incomplete"] = 0
        self.assertEqual(self.names("acim 100", rows), ["Acim 100 Aaa", "Acim 100 Bbb"])

    def test_the_order_is_deterministic_whatever_order_the_rows_arrive_in(self):
        import random
        rows = [row(i, f"Dolo {650 + (i % 3)} Tablet") for i in range(1, 8)] + [row(20, "Dolo 650 Tablet"), row(21, "Dolo 650 Tablet")]
        expected = [r["medicine_id"] for r in self.s.rank_rows("dolo 650", rows)]
        for seed in range(10):
            shuffled = rows[:]
            random.Random(seed).shuffle(shuffled)
            self.assertEqual([r["medicine_id"] for r in self.s.rank_rows("dolo 650", shuffled)], expected)

    def test_the_limit_is_honoured(self):
        rows = [row(i, f"Dolo{i} 650 Tablet") for i in range(1, 40)]
        self.assertEqual(len(self.s.rank_rows("dolo 650", rows, limit=5)), 5)


class SearchOnRealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from app.models.medicine_model import search_medicines_for_picker
        cls.search = staticmethod(search_medicines_for_picker)

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def test_every_spelling_of_pan_d_finds_the_brand_first(self):
        for q in ("Pan D", "Pan-D", "pan - D", "T. pan - D", "PAN-D"):
            results = self.search(q)
            self.assertEqual(results[0]["medicine_name"], "Pan-D Capsule PR", q)

    def test_vitamin_d3_60000_is_found_by_ingredient_and_by_brand_style(self):
        for q in ("vitamin d3 60000 capsule", "Vitamin D3 60,000", "D3 60K capsule", "D3 60 K capsule"):
            results = self.search(q)
            self.assertGreaterEqual(len(results), 5, q)
            top = results[:8]
            self.assertTrue(all("60" in (r["composition"] or "") + r["medicine_name"] for r in top), q)

    def test_ingredient_search_with_several_words(self):
        results = self.search("calcium carbonate vitamin d3")
        self.assertTrue(results)
        for r in results:
            self.assertIn("calcium carbonate", r["composition"].lower())
            self.assertIn("vitamin d3", r["composition"].lower())

    def test_release_type_in_the_query(self):
        sr = self.search("Metformin 500 SR")
        self.assertTrue(sr)
        self.assertEqual(sr[0]["release_type"], "sr")
        self.assertEqual(sr[0]["composition"], "Metformin (500mg)")
        plain = self.search("Metformin 500")
        self.assertIsNone(plain[0]["release_type"])
        self.assertEqual(plain[0]["composition"], "Metformin (500mg)")

    def test_a_well_known_brand_is_first(self):
        self.assertEqual(self.search("Dolo 650")[0]["medicine_name"], "Dolo 650 Tablet")
        self.assertEqual(self.search("dolo-650")[0]["medicine_name"], "Dolo 650 Tablet")
        self.assertEqual(self.search("Telma 40")[0]["medicine_name"], "Telma 40 Tablet")

    def test_the_spelling_fallback_still_reaches_the_datasets_spelling(self):
        names = [r["medicine_name"] for r in self.search("Amoxicillin")]
        self.assertTrue(any(n.lower().startswith("amox") for n in names))

    def test_what_comes_back_is_enough_to_tell_products_apart(self):
        for r in self.search("Metformin 500")[:5] + self.search("Pan D")[:3]:
            for key in ("medicine_id", "medicine_name", "composition", "form", "strength", "manufacturer", "pack_size", "price", "is_discontinued", "release_type", "composition_incomplete"):
                self.assertIn(key, r, key)

    def test_nothing_or_nonsense_returns_nothing_and_the_limit_holds(self):
        self.assertEqual(self.search(""), [])
        self.assertEqual(self.search("a"), [])
        self.assertEqual(self.search("tablet"), [])
        self.assertEqual(self.search("zzzzqqqxxyy"), [])
        self.assertLessEqual(len(self.search("calcium", limit=7)), 7)

    def test_searching_is_fast_enough_for_typing(self):
        started = time.time()
        for q in ("Pan D", "Metformin 500", "calcium carbonate vitamin d3", "Dolo 650"):
            self.search(q)
        self.assertLess((time.time() - started) / 4, 4.0)      # seconds per search; measured about 1.3


class Routes(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.client = self.app.test_client()
        self.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        with self.app.app_context():
            self.uid = self.accounts.user(allergies=[])
            self.other = self.accounts.user(allergies=[])
            self.pid = self.accounts.prescription(self.uid)
            self.other_pid = self.accounts.prescription(self.other)
            self.second_pid = self.accounts.prescription(self.uid)
            self.h = {"Authorization": f"Bearer {create_access_token(identity=str(self.uid))}"}
            self.h_other = {"Authorization": f"Bearer {create_access_token(identity=str(self.other))}"}
            self.pm = self.accounts.line(self.pid, None, raw_text="T. pan - D 100", status="needs_verification", confidence=0.66)
            self.pm_second = self.accounts.line(self.second_pid, None, raw_text="x", status="needs_verification", confidence=0.5)
            self.pm_other = self.accounts.line(self.other_pid, None, raw_text="y", status="needs_verification", confidence=0.5)
            self.dolo = self._medicine_id("Dolo 650 Tablet")
            self.telma = self._medicine_id("Telma 40 Tablet")

    def tearDown(self):
        with self.app.app_context():
            self.accounts.cleanup()

    def _medicine_id(self, name):
        from app.db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT medicine_id FROM Medicines WHERE medicine_name = %s LIMIT 1", (name,))
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

    def count(self, table):
        from app.db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        value = cur.fetchone()[0]
        cur.close()
        conn.close()
        return value

    # ---- the search endpoint ---------------------------------------------------------------
    def test_search_needs_a_login_and_a_real_query(self):
        self.assertEqual(self.client.get("/api/medicines/search?q=pan").status_code, 401)
        r = self.client.get("/api/medicines/search?q=p", headers=self.h)
        self.assertEqual((r.status_code, r.get_json()["medicines"]), (200, []))
        self.assertIn("at least 2", r.get_json()["message"])

    def test_search_returns_composition_release_type_and_a_readable_release_label(self):
        r = self.client.get("/api/medicines/search?q=Metformin 500 SR", headers=self.h)
        self.assertEqual(r.status_code, 200)
        first = r.get_json()["medicines"][0]
        self.assertEqual((first["release_type"], first["release_label"]), ("sr", "sustained release"))
        self.assertEqual(first["composition"], "Metformin (500mg)")
        self.assertIn("composition_incomplete", first)
        plain = self.client.get("/api/medicines/search?q=Dolo 650", headers=self.h).get_json()["medicines"][0]
        self.assertEqual((plain["medicine_name"], plain["release_type"], plain["release_label"]), ("Dolo 650 Tablet", None, None))
        self.assertEqual(r.get_json()["count"], len(r.get_json()["medicines"]))

    def test_searching_never_changes_any_data_or_confirms_anything(self):
        before = (self.count("Prescription_Medicines"), self.count("Price_Comparison"), self.count("Medicines"), dict(self.pm_row(self.pm)))
        for q in ("Pan D", "Metformin 500", "T. pan - D 100"):
            self.assertEqual(self.client.get(f"/api/medicines/search?q={q}", headers=self.h).status_code, 200)
        after = (self.count("Prescription_Medicines"), self.count("Price_Comparison"), self.count("Medicines"), dict(self.pm_row(self.pm)))
        self.assertEqual(before, after)
        self.assertEqual(self.pm_row(self.pm)["match_status"], "needs_verification")

    # ---- confirming a line ------------------------------------------------------------------
    def patch(self, pid, pm, body, headers=None):
        return self.client.patch(f"/api/prescriptions/{pid}/medicines/{pm}", json=body, headers=headers or self.h)

    def test_confirming_saves_exactly_the_chosen_medicine_and_clears_the_guess(self):
        # the line says "T. pan - D 100": Dolo 650 clearly conflicts with it, so it is held until acknowledged
        held = self.patch(self.pid, self.pm, {"medicine_id": self.dolo})
        self.assertEqual(held.status_code, 409)
        self.assertEqual(self.pm_row(self.pm)["match_status"], "needs_verification")
        r = self.patch(self.pid, self.pm, {"medicine_id": self.dolo, "acknowledge_warnings": True})
        self.assertEqual(r.status_code, 200)
        saved = self.pm_row(self.pm)
        self.assertEqual(saved["medicine_id"], self.dolo)
        self.assertEqual(saved["match_status"], "user_confirmed")
        self.assertIsNone(saved["match_confidence"])
        self.assertIsNone(saved["match_options"])
        self.assertEqual(saved["raw_text"], "T. pan - D 100")               # what the OCR read is kept as it was
        # and the analysis was regenerated from the confirmation
        from app.services.price_comparison_service import get_annotated_price_comparison
        with self.app.app_context():
            rows = get_annotated_price_comparison(self.pid)
        self.assertTrue(any(x["row_type"] == "prescribed" and x["pm_id"] == self.pm and x["medicine_id"] == self.dolo for x in rows))
        # confirming again, or changing the answer, works
        ack = lambda mid: {"medicine_id": mid, "acknowledge_warnings": True}
        self.assertEqual(self.patch(self.pid, self.pm, ack(self.dolo)).status_code, 200)
        self.assertEqual(self.patch(self.pid, self.pm, ack(self.telma)).status_code, 200)
        self.assertEqual(self.pm_row(self.pm)["medicine_id"], self.telma)

    def test_bad_ids_are_rejected_and_nothing_is_saved(self):
        for body in ({}, {"medicine_id": "5"}, {"medicine_id": None}, {"medicine_id": 1.5}, {"medicine_id": True}, {"medicine_id": False}, {"medicine_id": [1]}):
            r = self.patch(self.pid, self.pm, body)
            self.assertEqual(r.status_code, 400, body)
        self.assertEqual(self.patch(self.pid, self.pm, {"medicine_id": 999999999}).status_code, 404)
        saved = self.pm_row(self.pm)
        self.assertEqual((saved["medicine_id"], saved["match_status"]), (None, "needs_verification"))

    def test_nobody_can_confirm_a_line_that_is_not_theirs(self):
        self.assertEqual(self.patch(self.pid, self.pm, {"medicine_id": self.dolo}, headers=self.h_other).status_code, 404)    # another account's prescription
        self.assertEqual(self.patch(self.pid, self.pm_second, {"medicine_id": self.dolo}).status_code, 404)                   # a line from a different prescription
        self.assertEqual(self.patch(self.pid, 999999999, {"medicine_id": self.dolo}).status_code, 404)                        # no such line
        self.assertEqual(self.client.patch(f"/api/prescriptions/{self.pid}/medicines/{self.pm}", json={"medicine_id": self.dolo}).status_code, 401)
        for pm in (self.pm, self.pm_second, self.pm_other):
            self.assertEqual(self.pm_row(pm)["match_status"], "needs_verification")

    def test_a_line_stays_unconfirmed_until_the_person_confirms_it(self):
        from app.routes.prescriptions import _run_medicine_detection
        with self.app.app_context():
            detected = _run_medicine_detection(self.second_pid, [{"text": "T. pan - D 100"}, {"text": "T Lincont 100"}, {"text": "Metformin"}])
        self.assertTrue(detected)
        self.assertTrue(all(d["status"] == "needs_verification" for d in detected))        # a similarity score confirms nothing
        for d in detected:
            self.assertIsNone(self.pm_row(d["pm_id"])["medicine_id"])

    # ---- adding a medicine by hand ----------------------------------------------------------
    def post(self, pid, body, headers=None):
        return self.client.post(f"/api/prescriptions/{pid}/medicines", json=body, headers=headers or self.h)

    def test_adding_a_medicine_by_hand_is_saved_as_confirmed_with_the_instructions_read(self):
        r = self.post(self.pid, {"medicine_id": self.telma, "dosage_text": "1 tab twice daily for 5 days"})
        self.assertEqual(r.status_code, 201)
        saved = self.pm_row(r.get_json()["pm_id"])
        self.assertEqual((saved["medicine_id"], saved["match_status"], saved["prescription_id"]), (self.telma, "user_confirmed", self.pid))
        self.assertEqual((saved["frequency"], saved["duration"]), ("Twice daily", "5 days"))
        plain = self.post(self.pid, {"medicine_id": self.dolo})
        self.assertEqual(self.pm_row(plain.get_json()["pm_id"])["raw_text"], "Added manually")

    def test_adding_by_hand_validates_the_id_and_the_owner(self):
        for body in ({}, {"medicine_id": "5"}, {"medicine_id": True}, {"medicine_id": None}):
            self.assertEqual(self.post(self.pid, body).status_code, 400, body)
        self.assertEqual(self.post(self.pid, {"medicine_id": 999999999}).status_code, 404)
        self.assertEqual(self.post(self.pid, {"medicine_id": self.dolo}, headers=self.h_other).status_code, 404)
        self.assertEqual(self.client.post(f"/api/prescriptions/{self.pid}/medicines", json={"medicine_id": self.dolo}).status_code, 401)

    # ---- removing a line --------------------------------------------------------------------
    def test_removing_a_line_removes_only_that_line_and_only_for_its_owner(self):
        url = lambda pid, pm: f"/api/prescriptions/{pid}/medicines/{pm}"
        self.assertEqual(self.client.delete(url(self.pid, self.pm), headers=self.h_other).status_code, 404)
        self.assertEqual(self.client.delete(url(self.pid, self.pm_second), headers=self.h).status_code, 404)
        self.assertEqual(self.client.delete(url(self.pid, 999999999), headers=self.h).status_code, 404)
        self.assertEqual(self.client.delete(url(self.pid, self.pm)).status_code, 401)
        self.assertIsNotNone(self.pm_row(self.pm))
        self.assertEqual(self.client.delete(url(self.pid, self.pm), headers=self.h).status_code, 200)
        self.assertIsNone(self.pm_row(self.pm))
        self.assertIsNotNone(self.pm_row(self.pm_second))
        self.assertIsNotNone(self.pm_row(self.pm_other))


if __name__ == "__main__":
    unittest.main()
