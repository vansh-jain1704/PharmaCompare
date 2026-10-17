"""Price-quality rules: pure-function tests, then real products from the dataset."""
import unittest

from tests import helpers
from app.services import price_quality as pq


class PackParsing(unittest.TestCase):
    def test_counts_volumes_and_weights_are_kept_apart(self):
        self.assertEqual(pq.parse_pack("strip of 15 tablets"), (15.0, "count"))
        self.assertEqual(pq.parse_pack("strip of 10 tablet sr"), (10.0, "count"))
        self.assertEqual(pq.parse_pack("vial of 1 Injection"), (1.0, "count"))
        self.assertEqual(pq.parse_pack("bottle of 100 ml Syrup"), (100.0, "ml"))
        self.assertEqual(pq.parse_pack("bottle of 1 Ltr Solution"), (1000.0, "ml"))
        self.assertEqual(pq.parse_pack("tube of 20 gm Cream"), (20.0, "g"))
        self.assertEqual(pq.parse_pack("vial of 100 mg Injection"), (100.0, "mg"))
        for bad in (None, "", "loose", "strip of 0 tablets"):
            self.assertIsNone(pq.parse_pack(bad), bad)

    def test_same_quantity_needs_same_amount_and_same_kind(self):
        self.assertTrue(pq.same_pack_quantity("strip of 10 tablets", "strip of 10 tablet sr"))
        self.assertFalse(pq.same_pack_quantity("strip of 15 tablets", "strip of 10 tablets"))
        self.assertFalse(pq.same_pack_quantity("strip of 10 tablets", "bottle of 10 ml Syrup"))  # 10 tablets != 10 ml
        self.assertFalse(pq.same_pack_quantity("bottle of 1 Ltr Solution", "bottle of 100 ml Solution"))
        self.assertTrue(pq.same_pack_quantity("bottle of 1000 ml Solution", "bottle of 1 Ltr Solution"))
        self.assertFalse(pq.same_pack_quantity(None, "strip of 10 tablets"))


class ExtremePriceRule(unittest.TestCase):
    def group(self, unit_prices, pack="strip of 10 tablets"):
        return [(p * 10, pack) for p in unit_prices]

    def test_small_groups_are_never_judged(self):
        self.assertIsNone(pq.group_stats(self.group([1, 2, 3, 4, 5, 6, 7])))  # 7 < MIN_GROUP_SIZE
        self.assertIsNotNone(pq.group_stats(self.group([1, 2, 3, 4, 5, 6, 7, 8])))

    def test_flags_only_beyond_ten_times_the_median(self):
        stats = pq.group_stats(self.group([5, 5, 5, 5, 5, 5, 5, 5]))  # median 5 per unit
        self.assertIsNone(pq.classify(10, "strip of 10 tablets", stats))              # 1/unit: 5x below, legitimate (generics)
        self.assertEqual(pq.classify(4, "strip of 10 tablets", stats), pq.FLAG_LOW)   # 0.4/unit < 0.5
        self.assertIsNone(pq.classify(5, "strip of 10 tablets", stats))               # exactly 1/10: not beyond it
        self.assertEqual(pq.classify(600, "strip of 10 tablets", stats), pq.FLAG_HIGH)  # 60/unit > 50
        self.assertIsNone(pq.classify(400, "strip of 10 tablets", stats))

    def test_judged_per_unit_not_per_pack(self):
        stats = pq.group_stats(self.group([5] * 8))
        # a 30-tablet strip at Rs 150 is 5/unit: normal, though 15x a 10-tablet strip's pack price
        self.assertIsNone(pq.classify(150, "strip of 30 tablets", stats))

    def test_unreadable_or_differently_measured_packs_are_not_judged(self):
        stats = pq.group_stats(self.group([5] * 8))
        self.assertIsNone(pq.classify(1, "loose", stats))
        self.assertIsNone(pq.classify(1, "bottle of 100 ml Syrup", stats))  # judged only against products measured the same way
        self.assertIsNone(pq.classify(1, "strip of 10 tablets", None))

    def test_zero_or_missing_price_is_not_a_unit_price(self):
        self.assertIsNone(pq.unit_price(0, "strip of 10 tablets"))
        self.assertIsNone(pq.unit_price(None, "strip of 10 tablets"))


class SavingsEligibility(unittest.TestCase):
    def ok(self, **over):
        args = dict(prescribed_price=100, prescribed_flag=None, prescribed_pack="strip of 10 tablets",
                    alt_price=60, alt_flag=None, alt_pack="strip of 10 tablets", alt_discontinued=False)
        args.update(over)
        return pq.counts_for_savings(**args)

    def test_a_clean_cheaper_same_pack_alternative_counts(self):
        self.assertTrue(self.ok())

    def test_each_disqualifier(self):
        self.assertFalse(self.ok(alt_pack="strip of 15 tablets"))
        self.assertFalse(self.ok(alt_flag=pq.FLAG_LOW))
        self.assertFalse(self.ok(prescribed_flag=pq.FLAG_HIGH))
        self.assertFalse(self.ok(alt_discontinued=True))
        self.assertFalse(self.ok(alt_price=0))
        self.assertFalse(self.ok(alt_price=100))   # not cheaper
        self.assertFalse(self.ok(alt_price=130))
        self.assertFalse(self.ok(prescribed_price=None))
        self.assertFalse(self.ok(alt_pack=None))


class RealProducts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def compare(self, name):
        from app.models.medicine_model import get_prescription_medicines
        from app.services.price_comparison_service import compare_prescription_medicine
        accounts = helpers.TempAccounts()
        try:
            pid = accounts.prescription(accounts.user())
            accounts.line(pid, name)
            return compare_prescription_medicine(get_prescription_medicines(pid)[0])
        finally:
            accounts.cleanup()

    def test_an_extreme_low_price_is_flagged_kept_and_not_counted(self):
        result = self.compare("Augmentin 625 Duo Tablet")
        by_name = {a["medicine_name"]: a for a in result["alternatives"]}
        apcil = by_name["Apcil Tablet"]            # Rs 6.98 against a Rs 160 median: kept in the list...
        self.assertEqual(apcil["price_flag"], pq.FLAG_LOW)
        self.assertFalse(apcil["counts_for_savings"])  # ...but never the saving
        self.assertIsNone(apcil["savings_percent"])
        self.assertIn("verify", apcil["price_flag_note"])
        counted = [a for a in result["alternatives"] if a["counts_for_savings"]]
        self.assertTrue(counted)
        self.assertTrue(all(a["price_flag"] is None and a["same_pack_quantity"] for a in counted))

    def test_alternatives_in_a_different_pack_do_not_count(self):
        result = self.compare("Telma 40 Tablet")   # a strip of 30; many alternatives are strips of 10
        for alt in result["alternatives"]:
            if not alt["same_pack_quantity"]:
                self.assertFalse(alt["counts_for_savings"], alt["medicine_name"])
                self.assertIsNone(alt["savings_percent"], alt["medicine_name"])
        self.assertTrue(any(a["counts_for_savings"] for a in result["alternatives"]))

    def test_same_quantity_alternatives_are_listed_first(self):
        result = self.compare("Dolo 650 Tablet")   # a strip of 15; cheaper strips of 10 exist
        packs = [a["same_pack_quantity"] for a in result["alternatives"]]
        self.assertTrue(packs[0])
        self.assertEqual(packs, sorted(packs, reverse=True))

    def test_no_zero_priced_alternative_is_ever_offered(self):
        from app.db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM Medicines WHERE price = 0")
        zero_priced = cur.fetchone()[0]
        cur.close()
        conn.close()
        self.assertGreater(zero_priced, 0)  # the dataset does hold zero-priced rows (the audit counts 4)
        from app.models.price_model import find_alternatives
        for alt in find_alternatives("Paracetamol", None, "650mg", "Tablet", 0, limit=500):
            self.assertGreater(float(alt["price"]), 0)

    def test_stored_rows_are_annotated_the_same_way(self):
        from app.routes.prescriptions import _rerun_analysis
        from app.services.price_comparison_service import get_annotated_price_comparison
        accounts = helpers.TempAccounts()
        try:
            pid = accounts.prescription(accounts.user())
            accounts.line(pid, "Augmentin 625 Duo Tablet")
            _rerun_analysis(pid)
            rows = get_annotated_price_comparison(pid)
            self.assertTrue(any(r["row_type"] == "alternative" and r["price_flag"] == pq.FLAG_LOW for r in rows))
            self.assertTrue(all("counts_for_savings" in r for r in rows))
            flagged = [r for r in rows if r["row_type"] == "alternative" and r["price_flag"]]
            self.assertTrue(all(not r["counts_for_savings"] and r["savings_percent"] is None for r in flagged))
        finally:
            accounts.cleanup()


if __name__ == "__main__":
    unittest.main()
