"""
Objectives 1 and 4: what a price is, where it came from and how old it is; and the keyed endpoint a pharmacy's own system can push reports to.

Nothing here claims a live connection. Every row this file writes lives under a zz_test_ source key, is a stated test, and is removed again:
a source is deleted with its pharmacies, observations and partner keys (ON DELETE CASCADE).
"""
import hashlib
import io
import os
import shutil
import tempfile
import unittest
import uuid
from datetime import date, datetime, timedelta
from unittest import mock

from tests import helpers

DOLO = 58235


def when(hours):
    return (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")


class Provenance(unittest.TestCase):
    def setUp(self):
        from app.services import price_provenance_service
        self.p = price_provenance_service

    def test_a_reference_price_says_where_it_came_from_and_how_old_the_snapshot_is_and_that_it_is_not_live(self):
        basis = self.p.reference_basis("2026-10-12T10:00:00", today=date(2026, 10, 18))
        self.assertEqual((basis["basis"], basis["live"], basis["imported_on"], basis["age_days"], basis["stale"]), ("reference_dataset", False, "2026-10-12", 6, False))
        self.assertEqual(basis["label"], "Reference price from the Indian Medicine Dataset (community project on GitHub), imported 12 Oct 2026 (6 days ago). Not a live price.")
        self.assertIn("source does not say when each price was true", basis["what_the_date_means"])

    def test_the_date_is_the_import_date_never_presented_as_when_the_price_was_valid(self):
        label = self.p.reference_basis("2026-10-12", today=date(2026, 10, 18))["label"]
        self.assertIn("imported", label)
        self.assertNotRegex(label, r"(?i)valid|as of|current|live price\b(?!\.)")

    def test_an_old_snapshot_is_called_old(self):
        basis = self.p.reference_basis("2025-01-05T10:00:00", today=date(2026, 10, 18))
        self.assertTrue(basis["stale"])
        self.assertIn("21 months ago", basis["label"])
        self.assertTrue(basis["label"].endswith("This snapshot is old, so the price may have changed."))
        with mock.patch("app.config.Config.REFERENCE_PRICE_STALE_DAYS", 10):
            self.assertTrue(self.p.reference_basis("2026-10-01", today=date(2026, 10, 18))["stale"])
            self.assertFalse(self.p.reference_basis("2026-10-10", today=date(2026, 10, 18))["stale"])

    def test_ages_read_naturally_and_a_future_date_is_not_negative(self):
        today = date(2026, 10, 18)
        self.assertIn("(today)", self.p.reference_basis("2026-10-18", today=today)["label"])
        self.assertIn("(1 day ago)", self.p.reference_basis("2026-10-17", today=today)["label"])
        future = self.p.reference_basis("2026-12-01", today=today)
        self.assertEqual(future["age_days"], 0)

    def test_every_accepted_kind_of_date_works_and_a_missing_one_is_stated(self):
        today = date(2026, 10, 18)
        for value in (datetime(2026, 10, 12, 9, 0), date(2026, 10, 12), "2026-10-12", "2026-10-12T09:00:00Z"):
            self.assertEqual(self.p.reference_basis(value, today=today)["imported_on"], "2026-10-12", value)
        for value in (None, "", "garbage", 5):
            basis = self.p.reference_basis(value, today=today)
            self.assertIsNone(basis["imported_on"], value)
            self.assertIn("import date is not recorded", basis["label"])
            self.assertFalse(basis["live"])


class LiveDataStatus(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.ctx = self.app.app_context()
        self.ctx.push()
        from app.models import offer_model
        from app.services import data_sources_service
        self.offers, self.sources = offer_model, data_sources_service
        self.keys = []

    def tearDown(self):
        for key in self.keys:
            self.offers.delete_source(key)
        self.ctx.pop()

    def feed(self, kind, hours=2):
        key = f"zz_test_{uuid.uuid4().hex[:8]}"
        self.keys.append(key)
        source = self.offers.upsert_source(key, "zz test feed", kind)
        pharmacy = self.offers.get_or_create_pharmacy(source, "Test Pharmacy", "Testville")
        self.offers.insert_observation(pharmacy, DOLO, None, "in_stock", 5, datetime.now() - timedelta(hours=hours))
        return key

    def test_with_no_feed_the_app_says_no_live_feed_is_connected(self):
        before = self.sources.live_data()
        if before["reports"] == 0:
            self.assertFalse(before["live_feed_connected"])
            self.assertIn("No live pharmacy price or stock feed is connected", before["statement"])
            self.assertIn("no stock level is known", before["statement"])

    def test_demo_data_never_counts_as_a_live_feed(self):
        before = self.sources.live_data()
        self.feed("synthetic_demo")
        after = self.sources.live_data()
        self.assertEqual((after["feeds"], after["reports"]), (before["feeds"], before["reports"]))
        self.assertEqual(after["live_feed_connected"], before["live_feed_connected"])

    def test_a_real_feed_is_reported_with_its_counts_and_latest_observation_and_still_called_reports_not_live(self):
        before = self.sources.live_data()
        self.feed("pharmacy_feed", hours=3)
        after = self.sources.live_data()
        self.assertTrue(after["live_feed_connected"])
        self.assertEqual((after["feeds"], after["pharmacies"], after["reports"]), (before["feeds"] + 1, before["pharmacies"] + 1, before["reports"] + 1))
        self.assertIsNotNone(after["latest_observed_at"])
        self.assertIn("They are reports, not a live connection to a pharmacy.", after["statement"])

    def test_the_registry_lists_a_feeds_freshness(self):
        key = self.feed("pharmacy_feed", hours=5)
        entry = next(s for s in self.sources.list_sources() if s["source_key"] == key)
        self.assertEqual((entry["pharmacies"], entry["observations"]), (1, 1))
        self.assertIsNotNone(entry["latest_observed_at"])
        self.assertIsNotNone(entry["latest_received_at"])
        reference = next(s for s in self.sources.list_sources() if s["kind"] == "reference_dataset")
        self.assertIsNone(reference["latest_observed_at"], "a reference dataset has no pharmacy observations")


class ThroughTheScreens(unittest.TestCase):
    """The payloads and the PDF carry the provenance."""

    @classmethod
    def setUpClass(cls):
        cls.app = helpers.get_app()
        cls.client = cls.app.test_client()
        cls.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        with cls.app.app_context():
            cls.uid = cls.accounts.user(allergies=[])
            cls.pid = cls.accounts.prescription(cls.uid)
            cls.accounts.line(cls.pid, "Dolo 650 Tablet", raw_text="Tab Dolo 650 mg", confidence=0.99)
            from app.services.price_comparison_service import run_price_comparison
            run_price_comparison(cls.pid)
            cls.h = {"Authorization": f"Bearer {create_access_token(identity=str(cls.uid))}"}

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.accounts.cleanup()

    def test_every_stored_price_row_carries_its_provenance(self):
        body = self.client.get(f"/api/prescriptions/{self.pid}", headers=self.h).get_json()
        rows = body["price_comparison"]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual((row["price_basis"]["basis"], row["price_basis"]["live"]), ("reference_dataset", False), row["row_type"])
            self.assertIn("Not a live price.", row["price_basis"]["label"])
            self.assertIn("imported", row["price_basis"]["label"])

    def test_the_payload_says_whether_any_live_feed_exists(self):
        body = self.client.get(f"/api/prescriptions/{self.pid}", headers=self.h).get_json()
        self.assertIn("statement", body["live_data"])
        self.assertEqual(body["price_basis"]["basis"], "reference_dataset")
        self.assertFalse(body["price_basis"]["live"])

    def test_the_offers_route_states_the_reference_price_basis(self):
        body = self.client.get(f"/api/medicines/{DOLO}/offers", headers=self.h).get_json()
        self.assertEqual(body["price_basis"]["basis"], "reference_dataset")
        self.assertIn("Not a live price.", body["price_basis"]["label"])

    def test_the_data_sources_route_carries_the_live_data_status(self):
        body = self.client.get("/api/data-sources").get_json()
        self.assertIn("live_feed_connected", body["live_data"])

    def test_the_pdf_says_where_the_prices_come_from_and_whether_any_feed_is_live(self):
        import pypdfium2 as pdfium
        from app.models.prescription_model import get_prescription_by_id
        from app.services.smart_report_service import build_report_pdf
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "r.pdf")
        with self.app.app_context():
            build_report_pdf(self.pid, get_prescription_by_id(self.pid), path)
        doc = pdfium.PdfDocument(path)
        text = " ".join(" ".join(doc[i].get_textpage().get_text_range() for i in range(len(doc))).split())
        doc.close()
        self.assertIn("Where these prices come from. Reference price from the Indian Medicine Dataset (community project on GitHub), imported", text)
        self.assertIn("Not a live price.", text)
        self.assertRegex(text, r"No live pharmacy price or stock feed is connected|pharmacy feeds? \(\d+ pharmac")


class PartnerFeed(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        from app.models import offer_model, partner_key_model
        from app.services import partner_feed_service
        self.offers, self.keys_model, self.feed = offer_model, partner_key_model, partner_feed_service
        self.feed.reset_rate_limits()
        self.source_key = f"zz_test_{uuid.uuid4().hex[:8]}"
        self.source_id = self.offers.upsert_source(self.source_key, "zz test partner", "pharmacy_feed")
        self.key_id, self.token = self.keys_model.create_key(self.source_id, "test key")
        self.sources_to_delete = [self.source_key]
        self.people = helpers.TempAccounts()
        self.person = self.people.user(allergies=[])

    def tearDown(self):
        for key in self.sources_to_delete:
            self.offers.delete_source(key)
        self.people.cleanup()
        self.feed.reset_rate_limits()
        self.ctx.pop()

    def post(self, body, token="__own__", **kwargs):
        headers = {} if token is None else {"X-Partner-Key": self.token if token == "__own__" else token}
        return self.client.post("/api/feeds/offers", json=body, headers=headers, **kwargs)

    def row(self, **over):
        base = {"pharmacy": "Test Pharmacy", "city": "Testville", "medicine_id": DOLO, "availability": "in_stock", "quantity": 12, "price": 31.5, "observed_at": when(1)}
        base.update(over)
        return base

    def stored(self):
        return self.offers.get_observations([DOLO]).get(DOLO, [])

    # ---- the keys ----------------------------------------------------------------------------------------------------------------

    def test_only_a_hash_of_the_key_is_stored(self):
        from app.db import get_connection
        self.assertTrue(self.token.startswith("pck_"))
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT key_prefix, key_hash FROM Partner_Keys WHERE key_id = %s", (self.key_id,))
        prefix, key_hash = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM Partner_Keys WHERE key_hash = %s OR key_prefix = %s", (self.token, self.token))
        raw_matches = cur.fetchone()[0]
        cur.close()
        conn.close()
        self.assertEqual(key_hash, hashlib.sha256(self.token.encode()).hexdigest())
        self.assertEqual(prefix, self.token[:8])
        self.assertEqual(raw_matches, 0, "the key itself is nowhere in the table")

    def test_listing_keys_never_shows_a_secret(self):
        mine = next(k for k in self.keys_model.list_keys() if k["key_id"] == self.key_id)
        self.assertEqual(set(mine), {"key_id", "label", "key_prefix", "created_at", "last_used_at", "revoked_at", "source_key", "source_name"})
        self.assertNotIn(self.token, repr(mine))

    def test_keys_are_unique_and_long(self):
        _, other = self.keys_model.create_key(self.source_id, "second")
        self.assertNotEqual(self.token, other)
        self.assertGreaterEqual(len(other), 40)

    # ---- authentication ----------------------------------------------------------------------------------------------------------

    def test_every_kind_of_bad_key_gets_the_same_answer(self):
        self.keys_model.revoke(self.key_id)
        answers = []
        for token in (None, "", "nope", "pck_" + "x" * 43, "pck_" + "y" * 500, self.token):
            r = self.post({"rows": [self.row()]}, token=token)
            self.assertEqual(r.status_code, 401, token)
            answers.append(r.get_json())
        self.assertEqual(len({repr(a) for a in answers}), 1, "unknown, malformed and revoked keys cannot be told apart")
        self.assertEqual(self.stored(), [])

    def test_a_key_for_a_demo_source_is_refused(self):
        key = f"zz_test_{uuid.uuid4().hex[:8]}"
        self.sources_to_delete.append(key)
        source = self.offers.upsert_source(key, "zz demo", "synthetic_demo")
        _, token = self.keys_model.create_key(source, "demo key")
        self.assertEqual(self.post({"rows": [self.row()]}, token=token).status_code, 401)

    def test_revoking_stops_a_key_at_once_and_a_second_revoke_does_nothing(self):
        self.assertEqual(self.post({"rows": [self.row()]}).status_code, 200)
        self.assertTrue(self.keys_model.revoke(self.key_id))
        self.assertFalse(self.keys_model.revoke(self.key_id))
        self.assertEqual(self.post({"rows": [self.row(observed_at=when(2))]}).status_code, 401)

    def test_a_login_token_is_not_a_partner_key(self):
        from flask_jwt_extended import create_access_token
        self.assertEqual(self.post({"rows": [self.row()]}, token=create_access_token(identity="1")).status_code, 401)

    # ---- what is accepted --------------------------------------------------------------------------------------------------------

    def test_valid_reports_are_stored_attributed_to_the_keys_feed_and_shown_with_their_age(self):
        r = self.post({"rows": [self.row(), self.row(pharmacy="Other Pharmacy", availability="limited", price="", quantity=3, observed_at=when(5))]})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        report = r.get_json()
        self.assertEqual((report["read"], report["imported"], report["duplicates"], report["rejected"], report["pharmacies"], report["dry_run"]), (2, 2, 0, [], 2, False))
        mine = [o for o in self.stored() if o["source_key"] == self.source_key]
        self.assertEqual({o["pharmacy_name"] for o in mine}, {"Test Pharmacy", "Other Pharmacy"})
        self.assertTrue(all(o["source_kind"] == "pharmacy_feed" for o in mine))
        offers = self.client.get(f"/api/medicines/{DOLO}/offers", headers=self.auth()).get_json()
        item = next(i for i in offers["items"] if i["pharmacy"] == "Test Pharmacy")
        self.assertEqual((item["availability"], item["price"], item["demo"], item["source"]), ("in_stock", 31.5, False, "zz test partner"))

    def auth(self):
        """A logged-in person's header, for reading what the partner's reports look like to a user."""
        from flask_jwt_extended import create_access_token
        return {"Authorization": f"Bearer {create_access_token(identity=str(self.person))}"}

    def test_a_row_is_judged_exactly_like_a_csv_row_and_the_others_still_go_in(self):
        r = self.post({"rows": [
            self.row(),
            self.row(observed_at=(datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M")),         # in the future
            self.row(observed_at=""),                                                                      # no time
            self.row(medicine_id=999999999),                                                               # not in the catalogue
            self.row(medicine_id="", medicine_name="No Such Brand Anywhere"),                              # unknown name
            self.row(availability="plenty"),                                                               # unknown stock word
            self.row(price="-5"),                                                                          # not a price
            self.row(price="", availability=""),                                                           # reports nothing
            self.row(pharmacy=""),                                                                         # no pharmacy
        ]})
        report = r.get_json()
        self.assertEqual((report["read"], report["imported"]), (9, 1))
        reasons = {x["row"]: x["reason"] for x in report["rejected"]}
        self.assertEqual(sorted(reasons), [2, 3, 4, 5, 6, 7, 8, 9])
        self.assertIn("in the future", reasons[2])
        self.assertIn("observed_at is missing", reasons[3])
        self.assertIn("not in the catalogue", reasons[4])
        self.assertIn("no catalogue product is named exactly", reasons[5])
        self.assertIn("not recognised", reasons[6])
        self.assertIn("plausible positive price", reasons[7])
        self.assertIn("neither a price nor a stock status", reasons[8])
        self.assertIn("names no pharmacy", reasons[9])

    def test_malformed_rows_are_rejected_with_a_reason_without_breaking_the_request(self):
        report = self.post({"rows": ["just text", {"pharmacy": ["list"], "medicine_id": DOLO, "observed_at": when(1)}, self.row(city="c" * 201), self.row(), {"unknown_column": 1}]}).get_json()
        reasons = {x["row"]: x["reason"] for x in report["rejected"]}
        self.assertEqual(report["imported"], 1)
        self.assertIn("not an object", reasons[1])
        self.assertIn("must be text or a number", reasons[2])
        self.assertIn("longer than 200", reasons[3])
        self.assertIn(5, reasons)

    def test_a_dry_run_validates_and_writes_nothing(self):
        r = self.post({"rows": [self.row()], "dry_run": True})
        self.assertEqual((r.get_json()["imported"], r.get_json()["dry_run"]), (1, True))
        self.assertEqual([o for o in self.stored() if o["source_key"] == self.source_key], [])

    def test_sending_the_same_report_twice_adds_nothing(self):
        body = {"rows": [self.row()]}
        self.assertEqual(self.post(body).get_json()["imported"], 1)
        again = self.post(body).get_json()
        self.assertEqual((again["imported"], again["duplicates"]), (0, 1))
        self.assertEqual(len([o for o in self.stored() if o["source_key"] == self.source_key]), 1)

    def test_a_partner_cannot_report_into_another_feed_or_as_demo_data(self):
        body = {"rows": [self.row()], "source_key": "indian_medicine_dataset", "kind": "synthetic_demo", "source": "elsewhere"}
        self.assertEqual(self.post(body).status_code, 200)
        kinds = {(o["source_key"], o["source_kind"]) for o in self.stored()}
        self.assertEqual(kinds, {(self.source_key, "pharmacy_feed")})

    # ---- the request as a whole --------------------------------------------------------------------------------------------------

    def test_a_request_that_cannot_be_read_is_refused_with_a_reason(self):
        cases = [(None, "send a JSON object"), ([], "send a JSON object"), ({}, "send a JSON object"), ({"rows": "x"}, "send a JSON object"), ({"rows": []}, "rows is empty")]
        for body, words in cases:
            r = self.post(body)
            self.assertEqual(r.status_code, 400, body)
            self.assertIn(words, r.get_json()["error"])
        not_json = self.client.post("/api/feeds/offers", data="not json", headers={"X-Partner-Key": self.token})
        self.assertEqual(not_json.status_code, 400)

    def test_too_many_rows_are_refused_before_any_is_stored(self):
        with mock.patch("app.config.Config.PARTNER_FEED_MAX_ROWS", 2):
            r = self.post({"rows": [self.row(observed_at=when(h)) for h in (1, 2, 3)]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("at most 2 rows", r.get_json()["error"])
        self.assertEqual([o for o in self.stored() if o["source_key"] == self.source_key], [])

    def test_an_oversized_request_is_refused(self):
        with mock.patch("app.config.Config.PARTNER_FEED_MAX_BYTES", 50):
            r = self.post({"rows": [self.row()]})
        self.assertEqual(r.status_code, 413)

    def test_a_key_that_asks_too_often_is_slowed_down_and_another_key_is_not(self):
        _, other_token = self.keys_model.create_key(self.source_id, "second")
        with mock.patch("app.config.Config.PARTNER_FEED_REQUESTS_PER_MINUTE", 2):
            codes = [self.post({"rows": [self.row(observed_at=when(h))]}).status_code for h in (1, 2, 3)]
            limited = self.post({"rows": [self.row(observed_at=when(4))]})
            other = self.post({"rows": [self.row(observed_at=when(5))]}, token=other_token)
        self.assertEqual(codes, [200, 200, 429])
        self.assertEqual(limited.headers["Retry-After"], "60")
        self.assertEqual(other.status_code, 200)

    def test_the_rate_window_forgets_old_calls(self):
        with mock.patch("app.config.Config.PARTNER_FEED_REQUESTS_PER_MINUTE", 1):
            self.assertFalse(self.feed.too_many_requests(99, now=1000.0))
            self.assertTrue(self.feed.too_many_requests(99, now=1030.0))
            self.assertFalse(self.feed.too_many_requests(99, now=1061.0))

    # ---- what the feed's record shows afterwards ----------------------------------------------------------------------------------

    def test_a_delivery_updates_the_keys_use_and_the_feeds_freshness_and_never_echoes_the_key(self):
        from app.db import get_connection
        from app.services import data_sources_service
        r = self.post({"rows": [self.row(), self.row(pharmacy="Second", observed_at=when(2))]})
        self.assertNotIn(self.token, r.get_data(as_text=True))
        self.assertNotIn(self.token, repr(r.headers))
        used = next(k for k in self.keys_model.list_keys() if k["key_id"] == self.key_id)["last_used_at"]
        self.assertIsNotNone(used)
        entry = next(s for s in data_sources_service.list_sources() if s["source_key"] == self.source_key)
        self.assertEqual((entry["record_count"], entry["observations"]), (2, 2))
        self.assertIsNotNone(entry["retrieved_at"])
        self.assertIsNotNone(entry["latest_observed_at"])
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM System_Logs WHERE details LIKE %s", (f"%{self.token}%",))
        self.assertEqual(cur.fetchone()[0], 0)
        cur.close()
        conn.close()

    def test_removing_the_source_removes_its_keys_pharmacies_and_reports(self):
        from app.db import get_connection
        self.post({"rows": [self.row()]})
        self.offers.delete_source(self.source_key)
        self.sources_to_delete = []
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM Partner_Keys WHERE key_id = %s", (self.key_id,))
        self.assertEqual(cur.fetchone()[0], 0)
        cur.close()
        conn.close()
        self.assertEqual([o for o in self.stored() if o["source_key"] == self.source_key], [])
        self.assertEqual(self.post({"rows": [self.row(observed_at=when(2))]}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
