"""
Regression tests for the matching-safety audit (the three combination defects and every other change
made to matching in that audit). Each test states the real-world failure it guards against.

The rule they all enforce: if the evidence is not enough, the answer is "needs_verification", never a
confident match to a medicine that might be wrong.
"""
import unittest

from tests import helpers


def _candidate(**over):
    base = {"medicine_id": 1, "medicine_name": "Brandx 10 Tablet", "composition": "Alpha (10mg)", "primary_salt": "Alpha",
            "secondary_salt": None, "form": "Tablet", "strength": "10mg", "release_type": None, "composition_incomplete": 0}
    base.update(over)
    return base


class GateUnitTests(unittest.TestCase):
    """The automatic-match gate, on synthetic candidates (no database)."""

    @classmethod
    def setUpClass(cls):
        helpers.get_app()
        import app.services.medicine_matching_service as M
        cls.M = M

    # ---- defect 1: unknown strength -------------------------------------------------------
    def test_a_product_with_no_strength_on_record_cannot_settle_a_line_that_states_one(self):
        na = _candidate(medicine_name="Glimnis MF Tablet", composition="Glimepiride (NA) + Metformin (NA)", primary_salt="Glimepiride", secondary_salt="Metformin")
        self.assertEqual(self.M._cannot_be_verified("Tab Glimepiride 4 + Metformin 500", na), "strength not on record")
        self.assertFalse(self.M._settles_automatically("Tab Glimepiride 4 + Metformin 500", 0.99, na, ["glimepiride", "metformin"]))

    def test_an_unknown_strength_is_fine_when_the_line_states_no_number_or_the_name_carries_it(self):
        na = _candidate(medicine_name="Floritex Tablet", composition="Pantoprazole (NA)", primary_salt="Pantoprazole")
        self.assertIsNone(self.M._cannot_be_verified("Floritex", na))                      # a brand, no number written
        named = _candidate(medicine_name="Bpc T 40 Tablet", composition="Telmisartan (NA)", primary_salt="Telmisartan")
        self.assertIsNone(self.M._cannot_be_verified("Bpc T 40", named))                   # 40 is in the name

    def test_a_known_strength_is_never_blocked_by_this_rule(self):
        self.assertIsNone(self.M._cannot_be_verified("Brandx 10", _candidate()))

    # ---- defect 2: extra ingredients ------------------------------------------------------
    def test_a_one_ingredient_line_cannot_settle_on_a_combination_with_extra_ingredients(self):
        combo = _candidate(medicine_name="StayHappi Levosulpiride+Esomeprazole 75mg/40mg Capsule", composition="Levosulpiride (75mg) + Esomeprazole (40mg)",
                           primary_salt="Levosulpiride", secondary_salt="Esomeprazole")
        self.assertEqual(self.M._cannot_be_verified("Cap Levosulpiride 75", combo), "contains ingredients the line does not name")
        self.assertFalse(self.M._settles_automatically("Cap Levosulpiride 75", 0.99, combo, ["levosulpiride"]))

    def test_naming_every_ingredient_or_naming_none_is_not_blocked(self):
        combo = _candidate(medicine_name="Zerodol-P Tablet", composition="Aceclofenac (100mg) + Paracetamol (325mg)", primary_salt="Aceclofenac", secondary_salt="Paracetamol")
        self.assertIsNone(self.M._cannot_be_verified("Tab Aceclofenac 100 + Paracetamol 325", combo))
        self.assertIsNone(self.M._cannot_be_verified("Zerodol-P", combo))   # a brand names no ingredient

    # ---- defect 3: incomplete ingredient list --------------------------------------------
    def test_an_incomplete_product_is_never_settled_automatically_whatever_its_score(self):
        incomplete = _candidate(medicine_name="DavaIndia Aspirin+Rosuvastatin+Clopidogrel 150mg/10mg/75mg Capsule",
                                composition="Aspirin (150mg) + Rosuvastatin (10mg)", primary_salt="Aspirin", secondary_salt="Rosuvastatin", composition_incomplete=1)
        self.assertEqual(self.M._cannot_be_verified("Cap Rosuvastatin 10 + Aspirin 150", incomplete), "incomplete ingredient list")
        for score in (0.5, 0.95, 1.0):
            self.assertFalse(self.M._settles_automatically("Cap Rosuvastatin 10 + Aspirin 150", score, incomplete, ["aspirin", "rosuvastatin"]), score)
        # even a line that spells the product's own name out in full
        self.assertFalse(self.M._settles_automatically(incomplete["medicine_name"], 1.0, incomplete, []))

    # ---- the confidence rule --------------------------------------------------------------
    def test_a_look_alike_name_below_the_bar_is_only_a_guess(self):
        c = _candidate(medicine_name="Serra N 100 mg/15 mg Tablet", composition="Nimesulide (100mg)", primary_salt="Nimesulide")
        self.assertFalse(self.M._settles_automatically("Tab Serrta 100 Tablet", 0.76, c, []))   # 91% similar word, different brand
        self.assertFalse(self.M._settles_automatically("Tab Serrta 100 Tablet", 0.89, c, []))
        self.assertTrue(self.M._settles_automatically("Tab Serrta 100 Tablet", self.M.AUTO_MATCH_MIN_CONFIDENCE, c, []))

    def test_exact_words_settle_a_line_even_at_a_modest_score(self):
        c = _candidate(medicine_name="Pan-D Capsule PR", composition="Domperidone (30mg) + Pantoprazole (40mg)", primary_salt="Domperidone", secondary_salt="Pantoprazole")
        self.assertTrue(self.M._settles_automatically("Pan D", 0.69, c, []))

    def test_only_exact_words_count_as_identity(self):
        self.assertTrue(self.M._covers_every_token("Pan D", "Pan-D Capsule PR", exact=True))
        self.assertFalse(self.M._covers_every_token("Serrta 100", "Serra N 100 mg/15 mg Tablet", exact=True))
        self.assertTrue(self.M._covers_every_token("Serrta 100", "Serra N 100 mg/15 mg Tablet"))  # the near-equal check still exists for ranking

    # ---- dosage-form words and trailing dosing terms --------------------------------------
    def test_form_words_are_not_part_of_the_name_similarity(self):
        self.assertEqual(self.M._without_form_words("allegra m tablet"), "allegra m")
        self.assertEqual(self.M._without_form_words("ab flo capsule"), "ab flo")
        self.assertEqual(self.M._without_form_words("tablet"), "tablet")      # a name that is only a form word is kept
        shared = self.M._similarity(self.M._without_form_words("rhvtrax 10 tablet"), self.M._without_form_words("allegra m tablet"))
        padded = self.M._similarity("rhvtrax 10 tablet", "allegra m tablet")
        self.assertLess(shared, 0.4)
        self.assertGreater(padded, shared + 0.2)   # the shared word used to add this much

    def test_trailing_dosing_words_do_not_count_against_a_name(self):
        for line in ("Dolo 650 SOS", "Dolo 650 BD", "Dolo 650 OD", "Dolo 650 TDS", "Dolo 650 x 5 days", "Dolo 650 1-0-1", "Dolo 650 ER"):
            self.assertTrue(self.M._covers_every_token(line, "Dolo 650 Tablet", exact=True), line)
        self.assertFalse(self.M._covers_every_token("Dolo 650 Foobar", "Dolo 650 Tablet", exact=True))


class RealProductTests(unittest.TestCase):
    """The same rules on real dataset rows."""

    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from app.services.medicine_matching_service import match_line
        cls.match = staticmethod(match_line)

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def not_matched(self, line):
        r = self.match(line)
        self.assertEqual(r["status"], "needs_verification", f"{line!r} -> {r['status']} {(r['medicine'] or {}).get('medicine_name')}")
        return r

    # ---- defect 1 -------------------------------------------------------------------------
    def test_products_with_unknown_strengths_do_not_match_any_strength(self):
        for line in ("Tab Glimepiride 4 + Metformin 500", "Tab Ofloxacin 400 + Ornidazole 500", "Tab Montelukast 20 + Fexofenadine 120",
                     "Tab Montelukast 10 + Fexofenadine 240", "Tab Aceclofenac 100 + Paracetamol 650"):
            self.not_matched(line)

    # ---- defect 2 -------------------------------------------------------------------------
    def test_a_single_ingredient_line_never_settles_on_a_combination(self):
        r = self.not_matched("Cap Levosulpiride 75")
        # a closest guess may still be shown, but it is only a guess: never confirmed, no medicine_id stored
        for line in ("Tab Amoxicillin 500", "Cap Omeprazole 20", "Tab Telmisartan 40", "Tab Aceclofenac 100", "Tab Metformin 500"):
            m = self.match(line)
            if m["status"] == "matched":
                self.assertNotIn("+", m["medicine"]["composition"], line)

    # ---- defect 3 -------------------------------------------------------------------------
    def test_an_incomplete_ingredient_list_is_never_a_confirmed_match(self):
        self.not_matched("Cap Rosuvastatin 10 + Aspirin 150")
        self.not_matched("Cap Rosuvastatin 20 + Aspirin 150")

    def test_even_the_incomplete_products_own_name_is_left_for_the_person(self):
        # these two match THEMSELVES automatically when the guard is switched off (checked by hand), so this
        # test fails if the guard is removed; a person can still confirm them (next tests)
        from app.db import get_connection
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        for name in ("Mancold 100mg/5mg/5mg Tablet", "Clonac 500mg/50mg/500mg Tablet"):
            cur.execute("SELECT composition_incomplete FROM Medicines WHERE medicine_name = %s LIMIT 1", (name,))
            row = cur.fetchone()
            self.assertIsNotNone(row, name)
            self.assertEqual(row["composition_incomplete"], 1, f"precondition: {name} is flagged incomplete")
            r = self.not_matched(name)
            self.assertIsNone(r.get("medicine") if r["status"] == "matched" else None)
        cur.close()
        conn.close()

    def test_candidate_rows_carry_the_incomplete_flag(self):
        from app.models.medicine_model import search_by_name_prefix, search_candidates
        rows = search_by_name_prefix(["davaindia"]) + search_candidates("+aspirin* +rosuvastatin* +clopidogrel*")
        self.assertTrue(rows)
        self.assertTrue(all("composition_incomplete" in r for r in rows))
        self.assertTrue(any(r["composition_incomplete"] == 1 for r in rows))

    def test_a_person_can_still_confirm_an_incomplete_product_by_hand(self):
        from app.db import get_connection
        from app.models.medicine_model import update_prescription_medicine_match
        accounts = helpers.TempAccounts()
        try:
            conn = get_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT medicine_id, medicine_name FROM Medicines WHERE composition_incomplete = 1 AND is_discontinued = 0 LIMIT 1")
            product = cur.fetchone()
            cur.close()
            conn.close()
            uid = accounts.user(allergies=[])
            pid = accounts.prescription(uid)
            pm = accounts.line(pid, None, raw_text="written by the doctor", status="needs_verification", confidence=None)
            update_prescription_medicine_match(pm, product["medicine_id"])
            from app.models.medicine_model import get_prescription_medicines
            row = get_prescription_medicines(pid)[0]
            self.assertEqual(row["match_status"], "user_confirmed")
            self.assertEqual(row["medicine_id"], product["medicine_id"])
        finally:
            accounts.cleanup()

    # ---- dosage-form words ----------------------------------------------------------------
    def test_a_shared_form_word_no_longer_turns_unrelated_names_into_a_match(self):
        # both used to be matched (Allegra-M, AB-Flo) because "Tablet"/"Capsule" lifted the name similarity to 0.606
        for line in ("Tab Rhvtrax 10 Tablet", "Tab Galltra 100 Capsule", "Tab Roon 10 Tablet"):
            r = self.match(line)
            self.assertNotEqual(r["status"], "matched", line)

    def test_look_alike_brands_are_not_settled_below_the_bar(self):
        r = self.match("Tab Serrta 100 Tablet")
        self.assertNotEqual(r["status"], "matched")

    # ---- trailing dosing terms ------------------------------------------------------------
    def test_trailing_dosing_terms_do_not_demote_a_correct_match(self):
        for line, expect in (("Dolo 650 SOS", "Dolo 650"), ("Tab Dolo 650 BD", "Dolo 650"), ("Tab Telma 40 OD", "Telma 40"),
                             ("Tab Dolo 650 1-0-1 x 5 days", "Dolo 650"), ("Tab Pantop 40 TDS x 7 days", "Pantop 40")):
            r = self.match(line)
            self.assertEqual(r["status"], "matched", line)
            self.assertIn(expect, r["medicine"]["medicine_name"], line)

    def test_generic_lines_with_trailing_terms_still_resolve(self):
        for line in ("Tab Paracetamol 650 SOS", "Tab Paracetamol 650 BD", "Tab Amlodipine 5 OD", "Cap Omeprazole 20 BD"):
            r = self.match(line)
            self.assertEqual(r["status"], "matched", line)

    # ---- release types: immediate-release versus sustained-release ------------------------
    def test_an_unmarked_generic_line_is_the_immediate_release_product_when_one_exists(self):
        # each of these has BOTH an immediate-release tablet and a modified-release product at that strength;
        # the text search used to rank the modified-release one first and it was accepted
        for line in ("Tab Diltiazem 180", "Tab Alprazolam 1.5", "Tab Lornoxicam 16", "Tab Bupropion 150",
                     "Tab Lamotrigine 150", "Tab Glipizide 10", "Tab Nifedipine 20", "Tab Gliclazide 60"):
            r = self.match(line)
            if r["status"] == "matched":
                self.assertIsNone(r["medicine"]["release_type"], f"{line}: matched {r['medicine']['medicine_name']} ({r['medicine']['release_type']})")
                self.assertEqual(r["medicine"]["form"], "Tablet", line)

    def test_a_marked_line_is_only_ever_its_own_release_type(self):
        for line, release in (("Tab Alprazolam 1.5 SR", "sr"), ("Tab Bupropion 150 ER", "er"), ("Tab Lamotrigine 150 SR", "sr"),
                              ("Tab Glipizide 10 SR", "sr"), ("Tab Nifedipine 20 SR", "sr"), ("Tab Paroxetine 37.5 PR", "pr"), ("Tab Fluvoxamine 200 CR", "cr")):
            r = self.match(line)
            if r["status"] == "matched":
                self.assertEqual(r["medicine"]["release_type"], release, f"{line}: matched {r['medicine']['medicine_name']}")

    def test_a_marker_that_does_not_exist_never_falls_back_to_immediate_release(self):
        # no extended-release 25 mg metformin exists: the line must not become the plain tablet
        r = self.match("Tab Metformin 25 XR")
        if r["status"] == "matched":
            self.assertEqual(r["medicine"]["release_type"], "er")

    def test_retard_and_chrono_products_are_modified_release_in_the_dataset(self):
        from app.db import get_connection
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""SELECT medicine_name, release_type FROM Medicines
                       WHERE (medicine_name REGEXP '(^|[^A-Za-z])retard([^A-Za-z]|$)' OR medicine_name REGEXP '(^|[^A-Za-z])chrono([^A-Za-z]|$)')
                         AND (form IN ('Tablet','Capsule') OR pack_size LIKE '%tablet%' OR pack_size LIKE '%capsule%') AND release_type IS NULL""")
        unclassified = cur.fetchall()
        cur.execute("SELECT medicine_name, release_type FROM Medicines WHERE medicine_name IN ('Chronol 500mg Tablet', 'Retardon 2mg Tablet')")
        lookalikes = cur.fetchall()
        cur.close()
        conn.close()
        self.assertEqual(unclassified, [], "products named Retard/Chrono with no release type")
        self.assertTrue(all(r["release_type"] is None for r in lookalikes), lookalikes)   # different words, not markers


class ReleaseMarkerUnitTests(unittest.TestCase):
    def test_retard_and_chrono_are_markers_but_look_alikes_and_ambiguous_words_are_not(self):
        from app.services.release_type import derive_release_type, detect_line_release
        pack = "strip of 10 tablets"
        self.assertEqual(derive_release_type("Angiblock Retard 20mg Tablet", pack, "Tablet"), "sr")
        self.assertEqual(derive_release_type("Colospa Retard Capsule", "strip of 10 capsules", "Capsule"), "sr")
        self.assertEqual(derive_release_type("Chrono 500mg Tablet", pack, "Tablet"), "modified")
        for name in ("Chronol 500mg Tablet", "Retardon 2mg Tablet", "Acemiz -MR Tablet", "Addwize OD 18mg Tablet", "Anxiblok TR 40mg Tablet", "Aricet LA 5mg Tablet", "Dolo 650 Tablet"):
            self.assertIsNone(derive_release_type(name, pack, "Tablet"), name)
        self.assertEqual(detect_line_release("Nifedipine 20 retard"), "sr")
        self.assertEqual(detect_line_release("Tab Nifedipine Retard 20 1-0-1"), "sr")
        self.assertEqual(detect_line_release("Valproate 500 chrono"), "modified")
        for line in ("Tab Aceclofenac MR", "Tab Telma 40 OD", "Chronol 500", "Dolo 650"):
            self.assertIsNone(detect_line_release(line), line)

    def test_a_marker_line_is_never_the_other_release_type(self):
        from app.services.release_type import detect_line_release
        self.assertNotEqual(detect_line_release("Metformin 500 SR"), detect_line_release("Metformin 500 ER"))
        self.assertEqual(detect_line_release("Metformin 500 XL"), "er")


if __name__ == "__main__":
    unittest.main()
