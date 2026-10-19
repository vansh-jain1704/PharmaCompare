"""
Multi-pharmacy price and stock reports: the strict importer, the honest wording, the API and the analysis payload.

The data this file writes is labelled synthetic_demo, lives under a zz_test_ source key, and is removed again in tearDown, so the real
tables stay as they were (empty until a real feed is imported). Nothing here is, or is presented as, a real pharmacy price.
"""
import csv
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta

from tests import helpers

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def hours_ago(hours):
    return (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")


class CleansUp(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.key = f"zz_test_{uuid.uuid4().hex[:8]}"
        self.keys = [self.key]

    def tearDown(self):
        from app.models.offer_model import delete_source
        for key in self.keys:
            delete_source(key)
        self.ctx.pop()

    def sources_left(self):
        from app.db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM Data_Sources WHERE source_key LIKE 'zz\\_test\\_%'")
        n = cur.fetchone()[0]
        cur.close()
        conn.close()
        return n


class FieldParsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.services import feed_import_service
        cls.f = feed_import_service

    def test_observed_at_is_required_and_cannot_be_in_the_future(self):
        now = datetime(2026, 10, 18, 12, 0)
        self.assertEqual(self.f.parse_observed_at("2026-10-18 09:30", now), datetime(2026, 10, 18, 9, 30))
        self.assertEqual(self.f.parse_observed_at("2026-10-17T08:00:00", now), datetime(2026, 10, 17, 8, 0))
        self.assertEqual(self.f.parse_observed_at("2026-10-01", now), datetime(2026, 10, 1))
        for bad in ("", "yesterday", "18/10/2026", "2026-13-40", "2026-10-19 12:00"):
            with self.assertRaises(self.f.RowRejected, msg=bad):
                self.f.parse_observed_at(bad, now)

    def test_prices_must_be_positive_numbers_and_may_be_absent(self):
        from decimal import Decimal
        self.assertEqual(self.f.parse_price("34.27"), Decimal("34.27"))
        self.assertEqual(self.f.parse_price("1,234.5"), Decimal("1234.50"))
        self.assertIsNone(self.f.parse_price(""))
        for bad in ("0", "-5", "free", "12abc", "99999999"):
            with self.assertRaises(self.f.RowRejected, msg=bad):
                self.f.parse_price(bad)

    def test_stock_words_are_mapped_and_unknown_words_are_rejected_not_read_as_unknown(self):
        for word, expected in (("in stock", "in_stock"), ("IN_STOCK", "in_stock"), ("Available", "in_stock"), ("low", "limited"),
                               ("out of stock", "out_of_stock"), ("unavailable", "out_of_stock"), ("", "unknown"), ("unknown", "unknown")):
            self.assertEqual(self.f.parse_availability(word), expected, word)
        for bad in ("maybe", "on order", "plenty", "42"):
            with self.assertRaises(self.f.RowRejected, msg=bad):
                self.f.parse_availability(bad)

    def test_quantity_is_a_whole_number(self):
        self.assertEqual(self.f.parse_quantity("12"), 12)
        self.assertIsNone(self.f.parse_quantity(""))
        for bad in ("-3", "1.5", "ten"):
            with self.assertRaises(self.f.RowRejected, msg=bad):
                self.f.parse_quantity(bad)

    def test_headers_accept_their_aliases(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8") as handle:
            handle.write("Pharmacy Name,Product,Stock,Reported At,Price\nA,Dolo 650 Tablet,in stock,2026-10-18 09:00,34\n")
        try:
            (line, row), = self.f.read_csv(handle.name)
        finally:
            os.unlink(handle.name)
        self.assertEqual(line, 2)
        self.assertEqual((row["pharmacy"], row["medicine_name"], row["availability"], row["observed_at"], row["price"]), ("A", "Dolo 650 Tablet", "in stock", "2026-10-18 09:00", "34"))


class ProductResolution(CleansUp):
    def resolve(self, **row):
        from app.db import get_connection
        from app.services import feed_import_service as f
        conn = get_connection()
        cur = conn.cursor()
        try:
            return f.resolve_medicine(row, cur)
        finally:
            cur.close()
            conn.close()

    def test_a_unique_name_resolves_and_the_match_is_case_insensitive(self):
        self.assertEqual(self.resolve(medicine_name="Dolo 650 Tablet"), 58235)
        self.assertEqual(self.resolve(medicine_name="dolo 650 TABLET"), 58235)

    def test_an_ambiguous_name_is_rejected_never_chosen(self):
        from app.services.feed_import_service import RowRejected
        with self.assertRaises(RowRejected) as caught:
            self.resolve(medicine_name="Azee 500 Tablet")
        self.assertIn("ambiguous", str(caught.exception))
        self.assertIn("pack_size", str(caught.exception))

    def test_a_pack_size_or_an_id_makes_it_exact(self):
        self.assertEqual(self.resolve(medicine_name="Azee 500 Tablet", pack_size="strip of 5 tablets"), 8)
        self.assertEqual(self.resolve(medicine_name="Azee 500 Tablet", pack_size="strip of 3 tablets"), 275)
        self.assertEqual(self.resolve(medicine_id="8"), 8)

    def test_unknown_missing_and_invalid_products_are_rejected(self):
        from app.services.feed_import_service import RowRejected
        for row in ({"medicine_name": "Not A Real Medicine 999"}, {"medicine_id": "999999999"}, {"medicine_id": "abc"}, {}, {"medicine_name": ""}):
            with self.assertRaises(RowRejected, msg=str(row)):
                self.resolve(**row)


class ImportingAFeed(CleansUp):
    def rows(self, *lines):
        from app.services.feed_import_service import _normalise_header
        header = ["pharmacy", "city", "medicine_name", "pack_size", "price", "availability", "quantity", "observed_at"]
        return [(i + 2, dict(zip(header, line))) for i, line in enumerate(lines)]

    def do_import(self, rows, **kw):
        from app.services.feed_import_service import import_feed
        return import_feed(rows, self.key, "Test feed (synthetic)", kind="synthetic_demo", **kw)

    def test_valid_rows_are_imported_with_their_pharmacies_and_nothing_else(self):
        report = self.do_import(self.rows(
            ("Demo Pharmacy A", "Demo City", "Dolo 650 Tablet", "", "30.50", "in_stock", "20", hours_ago(2)),
            ("Demo Pharmacy B", "Demo City", "Dolo 650 Tablet", "", "33", "out_of_stock", "", hours_ago(5)),
            ("Demo Pharmacy A", "Demo City", "Azee 500 Tablet", "strip of 5 tablets", "", "limited", "3", hours_ago(1)),
        ))
        self.assertEqual((report["read"], report["imported"], report["duplicates"], report["rejected"], report["pharmacies"]), (3, 3, 0, [], 2))
        from app.models.offer_model import counts_for_source
        self.assertEqual(counts_for_source(self.key), (2, 3))

    def test_rows_that_cannot_be_trusted_are_rejected_with_the_reason(self):
        report = self.do_import(self.rows(
            ("Demo Pharmacy A", "", "Dolo 650 Tablet", "", "30", "in_stock", "", hours_ago(2)),           # fine
            ("Demo Pharmacy A", "", "Dolo 650 Tablet", "", "30", "in_stock", "", ""),                     # no time
            ("Demo Pharmacy A", "", "Azee 500 Tablet", "", "30", "in_stock", "", hours_ago(2)),          # ambiguous product
            ("Demo Pharmacy A", "", "Zzz Unknown 1", "", "30", "in_stock", "", hours_ago(2)),            # unknown product
            ("Demo Pharmacy A", "", "Dolo 650 Tablet", "", "0", "in_stock", "", hours_ago(3)),           # impossible price
            ("Demo Pharmacy A", "", "Dolo 650 Tablet", "", "30", "plenty", "", hours_ago(4)),            # unrecognised stock word
            ("Demo Pharmacy A", "", "Dolo 650 Tablet", "", "", "", "", hours_ago(5)),                    # reports nothing
            ("", "", "Dolo 650 Tablet", "", "30", "in_stock", "", hours_ago(6)),                         # no pharmacy
            ("Demo Pharmacy A", "", "Dolo 650 Tablet", "", "30", "in_stock", "", (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M")),  # future
        ))
        self.assertEqual(report["imported"], 1)
        reasons = " | ".join(reason for _, reason, _ in report["rejected"])
        for needle in ("no time is not accepted", "ambiguous", "no catalogue product", "plausible positive price", "not recognised", "neither a price nor a stock", "no pharmacy", "in the future"):
            self.assertIn(needle, reasons)
        self.assertEqual(len(report["rejected"]), 8)
        self.assertEqual([line for line, _, _ in report["rejected"]][0], 3)          # line numbers point at the file

    def test_importing_the_same_feed_twice_adds_nothing(self):
        rows = self.rows(("Demo Pharmacy A", "", "Dolo 650 Tablet", "", "30", "in_stock", "", hours_ago(2)))
        self.assertEqual(self.do_import(rows)["imported"], 1)
        again = self.do_import(rows)
        self.assertEqual((again["imported"], again["duplicates"]), (0, 1))
        from app.models.offer_model import counts_for_source
        self.assertEqual(counts_for_source(self.key), (1, 1))

    def test_a_dry_run_writes_nothing_not_even_the_source(self):
        report = self.do_import(self.rows(("Demo Pharmacy A", "", "Dolo 650 Tablet", "", "30", "in_stock", "", hours_ago(2))), dry_run=True)
        self.assertEqual((report["imported"], report["dry_run"]), (1, True))
        from app.models.offer_model import counts_for_source
        self.assertEqual(counts_for_source(self.key), (0, 0))
        self.assertEqual(self.sources_left(), 0)

    def test_only_the_two_known_kinds_are_accepted(self):
        from app.services.feed_import_service import import_feed
        with self.assertRaises(ValueError):
            import_feed([], self.key, "x", kind="live_prices")

    def test_removing_a_source_removes_its_pharmacies_and_observations(self):
        self.do_import(self.rows(("Demo Pharmacy A", "", "Dolo 650 Tablet", "", "30", "in_stock", "", hours_ago(2))))
        from app.models.offer_model import counts_for_source, delete_source, get_observations
        self.assertEqual(delete_source(self.key), 1)
        self.assertEqual(counts_for_source(self.key), (0, 0))
        self.assertEqual(get_observations([58235]), {})


class HonestWording(unittest.TestCase):
    """describe(): every figure with its source and age; stale stock never counts as in stock; no reports means 'not reported'."""

    @classmethod
    def setUpClass(cls):
        from app.services import offer_service
        cls.s = offer_service
        cls.now = datetime(2026, 10, 18, 12, 0)

    def row(self, pharmacy, hours, price=None, availability="unknown", pharmacy_id=None, kind="pharmacy_feed", qty=None):
        return {"pharmacy_id": pharmacy_id or abs(hash(pharmacy)) % 1000, "pharmacy_name": pharmacy, "city": "C", "price": price,
                "availability": availability, "quantity_available": qty, "observed_at": self.now - timedelta(hours=hours),
                "source_name": "Feed X", "source_kind": kind, "medicine_id": 1}

    def test_no_reports_say_not_reported_and_never_in_stock(self):
        d = self.s.describe([], self.now)
        self.assertEqual((d["count"], d["items"], d["cheapest"]), (0, [], None))
        self.assertEqual(d["availability"]["status"], "not_reported")
        self.assertNotIn("in stock", d["availability"]["label"].lower().replace("no pharmacy has reported stock", ""))

    def test_fresh_in_stock_reports_are_a_statement_about_now(self):
        d = self.s.describe([self.row("A", 2, 30, "in_stock"), self.row("B", 5, 33, "in_stock")], self.now)
        self.assertEqual(d["availability"]["status"], "in_stock")
        self.assertIn("In stock at 2 of 2 pharmacy reports", d["availability"]["label"])
        self.assertIn("2 hours ago", d["availability"]["label"])

    def test_a_stale_stock_report_is_not_counted_as_in_stock(self):
        d = self.s.describe([self.row("A", 100, 30, "in_stock")], self.now)
        self.assertEqual(d["availability"]["status"], "stale")
        self.assertIn("may have changed", d["availability"]["label"])
        self.assertIn("4 days ago", d["availability"]["label"])
        self.assertTrue(d["items"][0]["stock_stale"])

    def test_mixed_limited_and_out_of_stock_are_worded_as_they_are(self):
        self.assertEqual(self.s.describe([self.row("A", 1, 30, "in_stock"), self.row("B", 1, 31, "out_of_stock")], self.now)["availability"]["status"], "mixed")
        self.assertEqual(self.s.describe([self.row("A", 1, 30, "limited")], self.now)["availability"]["status"], "limited")
        out = self.s.describe([self.row("A", 1, None, "out_of_stock"), self.row("B", 3, None, "out_of_stock")], self.now)["availability"]
        self.assertEqual(out["status"], "out_of_stock")
        self.assertIn("all 2 reporting pharmacies", out["label"])

    def test_a_price_only_report_says_nothing_about_stock(self):
        d = self.s.describe([self.row("A", 1, 30, "unknown")], self.now)
        self.assertEqual(d["availability"]["status"], "not_reported")
        self.assertEqual(d["cheapest"]["price"], 30.0)

    def test_the_cheapest_price_is_the_cheapest_FRESH_one(self):
        d = self.s.describe([self.row("Old", 24 * 20, 10, "unknown"), self.row("New", 3, 40, "unknown"), self.row("New2", 4, 35, "unknown")], self.now)
        self.assertEqual(d["cheapest"]["pharmacy"], "New2")                       # the Rs 10 report is 20 days old
        old = next(i for i in d["items"] if i["pharmacy"] == "Old")
        self.assertTrue(old["price_stale"])
        self.assertEqual(old["age"], "20 days ago")

    def test_only_each_pharmacys_newest_report_counts(self):
        rows = [self.row("A", 2, 30, "in_stock", pharmacy_id=7), self.row("A", 30, 25, "out_of_stock", pharmacy_id=7)]
        d = self.s.describe(rows, self.now)
        self.assertEqual(d["count"], 1)
        self.assertEqual((d["items"][0]["price"], d["items"][0]["availability"]), (30.0, "in_stock"))

    def test_demo_data_is_always_labelled(self):
        d = self.s.describe([self.row("Demo", 1, 30, "in_stock", kind="synthetic_demo")], self.now)
        self.assertTrue(d["has_demo_data"])
        self.assertTrue(d["items"][0]["demo"])
        self.assertIn("not a real pharmacy", d["items"][0]["note"])
        self.assertFalse(self.s.describe([self.row("Real", 1, 30, "in_stock")], self.now)["has_demo_data"])

    def test_every_item_names_its_source_and_age(self):
        item = self.s.describe([self.row("A", 3, 30, "in_stock")], self.now)["items"][0]
        self.assertEqual((item["source"], item["age"]), ("Feed X", "3 hours ago"))
        self.assertTrue(item["observed_at"].startswith("2026-10-18T09:00"))

    def test_the_age_limits_are_the_documented_policy_settings(self):
        from app.config import Config
        self.assertEqual((Config.OFFER_STOCK_MAX_AGE_HOURS, Config.OFFER_PRICE_MAX_AGE_DAYS), (48, 7))


class ThroughTheApi(CleansUp):
    def setUp(self):
        super().setUp()
        self.client = self.app.test_client()
        self.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        self.uid = self.accounts.user(allergies=[])
        self.h = {"Authorization": f"Bearer {create_access_token(identity=str(self.uid))}"}
        self.dolo, self.azee = 58235, 8

    def tearDown(self):
        self.accounts.cleanup()
        super().tearDown()

    def load(self):
        from app.services.feed_import_service import import_feed
        header = ["pharmacy", "city", "medicine_name", "pack_size", "price", "availability", "quantity", "observed_at"]
        rows = [(2, dict(zip(header, ("Demo Pharmacy A", "Demo City", "Dolo 650 Tablet", "", "30.50", "in_stock", "20", hours_ago(2))))),
                (3, dict(zip(header, ("Demo Pharmacy B", "Demo City", "Dolo 650 Tablet", "", "33", "out_of_stock", "", hours_ago(3)))))]
        return import_feed(rows, self.key, "Test feed (synthetic)", kind="synthetic_demo")

    def test_the_endpoint_needs_a_login_and_a_real_medicine(self):
        self.assertEqual(self.client.get(f"/api/medicines/{self.dolo}/offers").status_code, 401)
        self.assertEqual(self.client.get("/api/medicines/999999999/offers", headers=self.h).status_code, 404)

    def test_a_medicine_nobody_reported_on_says_so_and_does_not_borrow_the_dataset_price(self):
        body = self.client.get(f"/api/medicines/{self.dolo}/offers", headers=self.h).get_json()
        self.assertEqual((body["count"], body["items"], body["cheapest"]), (0, [], None))
        self.assertEqual(body["availability"]["status"], "not_reported")
        self.assertNotIn("34.27", str(body))                                       # the dataset's reference price is not a pharmacy offer

    def test_reports_are_returned_with_source_age_and_demo_label(self):
        self.load()
        body = self.client.get(f"/api/medicines/{self.dolo}/offers", headers=self.h).get_json()
        self.assertEqual(body["count"], 2)
        self.assertEqual([i["pharmacy"] for i in body["items"]], ["Demo Pharmacy A", "Demo Pharmacy B"])      # cheapest first
        self.assertTrue(body["has_demo_data"])
        self.assertTrue(all(i["demo"] and i["source"] == "Test feed (synthetic)" for i in body["items"]))
        self.assertEqual(body["cheapest"]["price"], 30.5)
        self.assertEqual(body["availability"]["status"], "mixed")

    def test_the_analysis_carries_offers_for_identified_lines_only(self):
        self.load()
        pid = self.accounts.prescription(self.uid)
        identified = self.accounts.line(pid, "Dolo 650 Tablet", raw_text="Tab Dolo 650", status="matched", confidence=1.0)
        unsettled = self.accounts.line(pid, None, raw_text="Tab Dolo 650 X", status="needs_verification", confidence=0.5)
        lines = {d["pm_id"]: d for d in self.client.get(f"/api/prescriptions/{pid}", headers=self.h).get_json()["detected_medicines"]}
        self.assertEqual(lines[identified]["offers"]["count"], 2)
        self.assertIsNone(lines[unsettled]["offers"])                               # an unidentified line is never matched to a pharmacy report

    def test_an_identified_medicine_with_no_reports_carries_an_honest_empty_state(self):
        pid = self.accounts.prescription(self.uid)
        pm = self.accounts.line(pid, "Zerodol-P Tablet", raw_text="Tab Zerodol-P", status="matched", confidence=1.0)
        line = {d["pm_id"]: d for d in self.client.get(f"/api/prescriptions/{pid}", headers=self.h).get_json()["detected_medicines"]}[pm]
        self.assertIsNone(line["offers"])


class InThePdf(CleansUp):
    def setUp(self):
        super().setUp()
        self.accounts = helpers.TempAccounts()
        self.uid = self.accounts.user(allergies=[])
        self.pid = self.accounts.prescription(self.uid)
        self.accounts.line(self.pid, "Dolo 650 Tablet", raw_text="Tab Dolo 650", status="matched", confidence=1.0)

    def tearDown(self):
        self.accounts.cleanup()
        super().tearDown()

    def pdf_text(self):
        import pypdfium2 as pdfium
        from app.models.prescription_model import get_prescription_by_id
        from app.routes.prescriptions import _rerun_analysis
        from app.services.smart_report_service import build_report_pdf
        _rerun_analysis(self.pid)
        path = os.path.join(tempfile.mkdtemp(), "report.pdf")
        build_report_pdf(self.pid, get_prescription_by_id(self.pid), path)
        pdf = pdfium.PdfDocument(path)
        try:
            return " ".join(" ".join(pdf[i].get_textpage().get_text_range().split()) for i in range(len(pdf)))
        finally:
            pdf.close()

    def test_with_no_reports_the_pdf_says_so_and_names_no_pharmacy(self):
        out = self.pdf_text()
        self.assertIn("Pharmacy prices and stock (as reported)", out)
        self.assertIn("No pharmacy has reported a price or stock", out)
        # the sentence now comes from the live-feed status, which says the same thing and also that no feed is connected
        self.assertIn("No live pharmacy price or stock feed is connected. Every price shown is a reference price from a dataset snapshot", out)
        self.assertIn("no stock level is known", out)

    def test_with_reports_the_pdf_lists_them_with_source_age_and_the_demo_label(self):
        from app.services.feed_import_service import import_feed
        header = ["pharmacy", "city", "medicine_name", "pack_size", "price", "availability", "quantity", "observed_at"]
        rows = [(2, dict(zip(header, ("Demo Pharmacy A", "Demo City", "Dolo 650 Tablet", "", "30.50", "in_stock", "", hours_ago(2)))))]
        import_feed(rows, self.key, "Test feed (synthetic)", kind="synthetic_demo")
        out = self.pdf_text()
        for needle in ("Demo Pharmacy A", "Demo City", "30.50", "In stock", "2 hours ago", "Test feed (synthetic) (demo)", "Demo data:", "not real pharmacies and not real prices",
                       "confirm with the pharmacy"):
            self.assertIn(needle, out)
        self.assertNotIn("No pharmacy has reported a price or stock", out)


class CommandLine(CleansUp):
    def run_script(self, *args):
        return subprocess.run([sys.executable, os.path.join("database", "import_pharmacy_feed.py"), *args], cwd=BACKEND,
                              capture_output=True, text=True, encoding="utf-8", timeout=120)

    def write_feed(self, lines):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8")
        writer = csv.writer(handle)
        writer.writerow(["pharmacy", "city", "medicine_name", "price", "availability", "observed_at"])
        writer.writerows(lines)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_dry_run_then_import_then_remove(self):
        feed = self.write_feed([("Demo Pharmacy A", "Demo City", "Dolo 650 Tablet", "30.50", "in_stock", hours_ago(2)),
                                ("Demo Pharmacy A", "Demo City", "Nope Not Real", "30", "in_stock", hours_ago(2))])
        rejects = feed + ".rejects.csv"
        self.addCleanup(lambda: os.path.exists(rejects) and os.unlink(rejects))
        dry = self.run_script(feed, "--source-key", self.key, "--name", "CLI test", "--kind", "synthetic_demo", "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("would import 1", dry.stdout)
        self.assertEqual(self.sources_left(), 0)
        real = self.run_script(feed, "--source-key", self.key, "--name", "CLI test", "--kind", "synthetic_demo", "--rejects", rejects)
        self.assertIn("imported 1", real.stdout)
        self.assertIn("rejected 1", real.stdout)
        self.assertIn("no catalogue product is named exactly", real.stdout)
        with open(rejects, encoding="utf-8") as fh:
            self.assertIn("Nope Not Real", fh.read())
        removed = self.run_script("--remove-source", self.key)
        self.assertIn("removed 1 source (1 pharmacies, 1 observations)", removed.stdout)
        self.assertEqual(self.sources_left(), 0)

    def test_the_arguments_are_checked(self):
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertNotEqual(self.run_script("x.csv", "--source-key", "k").returncode, 0)
        feed = self.write_feed([])
        self.assertNotEqual(self.run_script(feed, "--source-key", self.key, "--name", "n", "--kind", "live_prices").returncode, 0)


if __name__ == "__main__":
    unittest.main()
