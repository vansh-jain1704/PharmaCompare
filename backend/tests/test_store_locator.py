"""
Finding medical stores and Jan Aushadhi Kendras near a place: an independent, location-only feature.

The Overpass replies in this file are SMALL SAMPLES WRITTEN FOR THE TESTS in OpenStreetMap's documented format. They are test inputs only:
no store in them exists, nothing from them is ever shown by the app, and no request leaves this machine (requests.post / requests.get are
mocked). Whether the live public server answers is NOT tested here.

What is proved: a store appears only if the reply lists it; nothing is invented or marked verified; contact details are shown only when
present and well formed; the position is rounded, not
stored and not logged; failures say so instead of returning an empty "no stores" answer; and the feature carries no medicine, stock,
price or prescription data and is not connected to any of it.
"""
import math
import os
import re
import unittest
from unittest import mock

import requests

from tests import helpers

ORIGIN = (28.614, 77.209)


def node(osm_id, name, lat, lon, **tags):
    return {"type": "node", "id": osm_id, "lat": lat, "lon": lon, "timestamp": "2026-03-14T09:30:00Z", "tags": {"amenity": "pharmacy", "name": name, **tags}}


SAMPLE = [
    node(1, "Pradhan Mantri Bhartiya Janaushadhi Kendra", 28.6150, 77.2100, phone="+91 11 2345 6789", **{"addr:street": "Test Road", "addr:housenumber": "12", "addr:city": "Testville", "addr:postcode": "110001"}),
    node(2, "Cure Generic Medicals", 28.6200, 77.2200, website="https://example.invalid/store", opening_hours="Mo-Sa 09:00-21:00"),
    node(3, "City Pharmacy", 28.6141, 77.2091),
    {"type": "way", "id": 4, "center": {"lat": 28.6300, "lon": 77.2300}, "tags": {"shop": "chemist", "brand": "Jan Aushadhi"}},
    node(5, "General Store Chemists", 28.6142, 77.2092),
]


class Coordinates(unittest.TestCase):
    def setUp(self):
        from app.services import store_locator_service
        self.svc = store_locator_service

    def test_positions_are_rounded_to_about_100_metres(self):
        self.assertEqual(self.svc.clean_coordinates("28.613912345", "77.209087654"), (28.614, 77.209))
        self.assertEqual(self.svc.clean_coordinates(-33.8688, 151.2093), (-33.869, 151.209))

    def test_bad_positions_are_refused(self):
        for lat, lon in [(None, 1), ("abc", 1), (91, 0), (-91, 0), (0, 181), (0, -181), (float("nan"), 1), (1, float("inf")), ("", "")]:
            with self.assertRaises(ValueError, msg=f"{lat!r},{lon!r}"):
                self.svc.clean_coordinates(lat, lon)

    def test_the_radius_is_kept_within_the_configured_limits(self):
        from app.config import Config
        self.assertEqual(self.svc.clean_radius_km("5"), 5.0)
        self.assertEqual(self.svc.clean_radius_km(0.01), self.svc.MIN_RADIUS_KM)
        self.assertEqual(self.svc.clean_radius_km(10 ** 6), float(Config.STORE_MAX_RADIUS_KM))
        for bad in ("x", 0, -3, float("nan"), None):
            with self.assertRaises(ValueError):
                self.svc.clean_radius_km(bad)

    def test_distance_is_the_great_circle_distance(self):
        self.assertEqual(self.svc.haversine_m(10, 20, 10, 20), 0)
        delhi_to_mumbai = self.svc.haversine_m(28.6139, 77.2090, 19.0760, 72.8777) / 1000
        self.assertTrue(1135 < delhi_to_mumbai < 1160, delhi_to_mumbai)
        self.assertAlmostEqual(self.svc.haversine_m(0, 0, 0, 1), 111195, delta=200)          # one degree of longitude at the equator

    def test_distance_text(self):
        self.assertEqual([self.svc.distance_text(m) for m in (42, 137, 999, 1530, 12400)], ["42 m", "140 m", "1000 m", "1.5 km", "12.4 km"])

    def test_directions_link_carries_only_the_stores_position(self):
        url = self.svc.directions_url(28.6150, 77.2100)
        self.assertEqual(url, "https://www.google.com/maps/dir/?api=1&destination=28.615000,77.210000")


class Classification(unittest.TestCase):
    def setUp(self):
        from app.services import store_locator_service
        self.svc = store_locator_service

    def test_jan_aushadhi_names_in_english_and_hindi(self):
        for name in ("Pradhan Mantri Bhartiya Janaushadhi Kendra", "Jan Aushadhi Kendra", "JAN-AUSHADHI", "PMBJP Kendra 4521", "जन औषधि केंद्र",
                     # spellings found in real OpenStreetMap listings: "Pradhana", and "Aushadi" with one h
                     "Pradhana Mantri Jan Aushadi Kendra", "Jana Aushadhi Kendra", "Janaushadi", "JanAushadhi", "Jan Aushdhi", "PMBJK 2209"):
            self.assertEqual(self.svc.classify({"name": name}), "jan_aushadhi", name)
        self.assertEqual(self.svc.classify({"name": "Medical Hall", "brand": "Jan Aushadhi"}), "jan_aushadhi")

    def test_generic_stores(self):
        for name in ("Cure Generic Medicals", "Generic Aadhaar", "जेनेरिक मेडिकल"):
            self.assertEqual(self.svc.classify({"name": name}), "generic", name)

    def test_other_pharmacies_and_look_alike_words_are_not_generic(self):
        for name in ("Apollo Pharmacy", "General Store Chemists", "Janata Medical", "Aushadhalaya", "Rajan Aushadhi Kendra", "Shree Aushadi Medicals", "Manjula Medicals"):
            self.assertEqual(self.svc.classify({"name": name}), "pharmacy", name)
        self.assertEqual(self.svc.classify({}), "pharmacy")


class ReadingElements(unittest.TestCase):
    def setUp(self):
        from app.services import store_locator_service
        self.svc = store_locator_service

    def stores(self, scope="generic", elements=None):
        return self.svc.parse_elements(SAMPLE if elements is None else elements, ORIGIN, scope)

    def test_generic_scope_keeps_only_jan_aushadhi_and_generic_stores_nearest_first(self):
        got = self.stores()
        self.assertEqual([s["store_id"] for s in got], ["osm:node/1", "osm:node/2", "osm:way/4"])
        self.assertEqual([s["category"] for s in got], ["jan_aushadhi", "generic", "jan_aushadhi"])
        self.assertEqual([s["distance_m"] for s in got], sorted(s["distance_m"] for s in got))

    def test_all_scope_adds_other_pharmacies(self):
        refs = [s["store_id"] for s in self.stores("all")]
        self.assertEqual(set(refs), {"osm:node/1", "osm:node/2", "osm:node/3", "osm:way/4", "osm:node/5"})
        self.assertEqual(refs[0], "osm:node/3")                                                  # the closest, once pharmacies count

    def test_a_listed_store_carries_what_the_listing_says_and_no_more(self):
        first = self.stores()[0]
        self.assertEqual(first["name"], "Pradhan Mantri Bhartiya Janaushadhi Kendra")
        self.assertEqual(first["address"], "12 Test Road, Testville, 110001")
        self.assertEqual((first["phone"], first["phone_link"]), ("+91 11 2345 6789", "tel:+911123456789"))
        self.assertEqual(first["listing_last_edited"], "2026-03-14")
        self.assertEqual(first["source"], "OpenStreetMap")
        self.assertIsNone(first["website"])
        self.assertIsNone(first["opening_hours"])
        second = self.stores()[1]
        self.assertEqual((second["website"], second["opening_hours"]), ("https://example.invalid/store", "Mo-Sa 09:00-21:00"))
        self.assertIsNone(second["phone"])                                                       # absent stays absent

    def test_nothing_is_ever_marked_verified(self):
        for store in self.stores("all"):
            self.assertIs(store["verified"], False)

    def test_an_area_with_no_listed_stores_gives_none_rather_than_invented_ones(self):
        self.assertEqual(self.stores(elements=[]), [])
        self.assertEqual(self.stores(elements=[node(3, "City Pharmacy", 1, 1)]), [])

    def test_ways_use_their_centre_and_broken_elements_are_skipped(self):
        broken = [
            {"type": "way", "id": 9, "tags": {"name": "Jan Aushadhi"}},                              # no position at all
            {"type": "node", "id": "x", "lat": 1, "lon": 1, "tags": {"name": "Jan Aushadhi"}},       # bad id
            {"type": "area", "id": 3, "lat": 1, "lon": 1, "tags": {"name": "Jan Aushadhi"}},         # not a node / way / relation
            {"type": "node", "id": 7, "lat": "1", "lon": 1, "tags": {"name": "Jan Aushadhi"}},       # position is not a number
            node(8, "Jan Aushadhi Kendra", 28.62, 77.21),
        ]
        self.assertEqual([s["store_id"] for s in self.stores(elements=broken)], ["osm:node/8"])
        self.assertEqual(self.stores()[2]["lat"], 28.63)

    def test_the_same_store_listed_twice_appears_once(self):
        self.assertEqual(len(self.stores(elements=[SAMPLE[0], dict(SAMPLE[0])])), 1)

    def test_a_listing_with_no_name_is_labelled_not_named_up(self):
        got = self.stores("all", [{"type": "node", "id": 10, "lat": 28.615, "lon": 77.21, "tags": {"amenity": "pharmacy"}}])
        self.assertEqual((got[0]["name"], got[0]["name_listed"]), ("Pharmacy — name unavailable", False))

    def test_phone_numbers_that_are_not_phone_numbers_are_dropped(self):
        for raw in ("javascript:alert(1)", "<b>call</b>", "123", "call me maybe", "x" * 80):
            got = self.stores(elements=[node(11, "Jan Aushadhi", 28.62, 77.21, phone=raw)])
            self.assertEqual((got[0]["phone"], got[0]["phone_link"]), (None, None), raw)

    def test_only_http_and_https_websites_are_kept(self):
        for raw, expected in (("javascript:alert(1)", None), ("ftp://x.invalid", None), ("example.invalid", None), ("http://a.invalid/x", "http://a.invalid/x")):
            got = self.stores(elements=[node(12, "Jan Aushadhi", 28.62, 77.21, website=raw)])
            self.assertEqual(got[0]["website"], expected, raw)

    def test_the_contact_phone_tag_is_used_when_phone_is_absent(self):
        got = self.stores(elements=[node(13, "Jan Aushadhi", 28.62, 77.21, **{"contact:phone": "+91 98765 43210"})])
        self.assertEqual(got[0]["phone_link"], "tel:+919876543210")

    def test_a_missing_or_malformed_timestamp_is_not_invented(self):
        for stamp in (None, "garbage"):
            el = node(14, "Jan Aushadhi", 28.62, 77.21)
            el.pop("timestamp")
            if stamp:
                el["timestamp"] = stamp
            self.assertIsNone(self.stores(elements=[el])[0]["listing_last_edited"])


class AskingOpenStreetMap(unittest.TestCase):
    def setUp(self):
        from app.config import Config
        from app.services import store_locator_service
        self.svc, self.config = store_locator_service, Config
        self.svc.clear_cache()
        self.addCleanup(self.svc.clear_cache)

    def reply(self, status=200, payload=None, text=None):
        r = mock.Mock(status_code=status)
        if text is not None:
            r.json.side_effect = ValueError("not json")
        else:
            r.json.return_value = {"elements": []} if payload is None else payload
        return r

    def test_the_query_uses_the_rounded_position_and_names_no_one(self):
        query = self.svc.build_query(28.614, 77.209, 5000, 400)
        self.assertIn("(around:5000,28.614,77.209)", query)
        self.assertIn('"amenity"="pharmacy"', query)
        self.assertIn("out center meta 400;", query)

    def test_the_request_identifies_the_application(self):
        with mock.patch("app.services.store_locator_service.requests.post", return_value=self.reply()) as post:
            self.svc.fetch_overpass("q")
        self.assertEqual(post.call_args.kwargs["headers"]["User-Agent"], self.config.PLACES_USER_AGENT)
        self.assertEqual(post.call_args.args[0], self.config.OVERPASS_URL)
        self.assertEqual(post.call_args.kwargs["timeout"][0], 5)                                   # a short connect timeout, so a dead server is skipped quickly

    def test_each_kind_of_failure_is_reported_not_turned_into_no_stores(self):
        cases = [
            (requests.Timeout("slow"), "could not be reached"),
            (requests.ConnectionError("down"), "could not be reached"),
            (self.reply(429), "busy"), (self.reply(502), "busy"), (self.reply(504), "busy"),
            (self.reply(500), "returned an error"),
            (self.reply(text="<html>"), "unreadable"),
            (self.reply(payload={"unexpected": 1}), "unexpected"),
            (self.reply(payload=[1, 2]), "unexpected"),
        ]
        for outcome, words in cases:
            effect = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
            with mock.patch("app.services.store_locator_service.requests.post", **effect):
                with self.assertRaises(self.svc.PlacesUnavailable) as caught:
                    self.svc.fetch_overpass("q")
            self.assertIn(words, str(caught.exception))

    def test_the_server_running_out_of_time_is_not_reported_as_an_empty_area(self):
        payload = {"elements": [], "remark": "runtime error: Query timed out in \"query\" at line 3 after 20 seconds."}
        with mock.patch("app.services.store_locator_service.requests.post", return_value=self.reply(payload=payload)):
            with self.assertRaises(self.svc.PlacesUnavailable) as caught:
                self.svc.fetch_overpass("q")
        self.assertIn("smaller distance", str(caught.exception))

    def test_a_busy_server_is_skipped_and_the_next_one_answers(self):
        urls = ["https://one.invalid/api", "https://two.invalid/api", "https://three.invalid/api"]
        outcomes = {urls[0]: self.reply(504), urls[1]: requests.Timeout("slow"), urls[2]: self.reply(payload={"elements": [{"type": "node", "id": 1}]})}
        calls = []

        def post(url, **kw):
            calls.append(url)
            result = outcomes[url]
            if isinstance(result, Exception):
                raise result
            return result
        with mock.patch("app.config.Config.OVERPASS_URL", urls[0]), mock.patch("app.config.Config.OVERPASS_FALLBACK_URLS", ",".join(urls[1:])),              mock.patch("app.services.store_locator_service.requests.post", side_effect=post):
            body = self.svc.fetch_overpass("q")
        self.assertEqual(calls, urls)
        self.assertEqual(body["elements"][0]["id"], 1)

    def test_the_first_server_that_answers_is_the_only_one_asked(self):
        with mock.patch("app.config.Config.OVERPASS_URL", "https://one.invalid/api"), mock.patch("app.config.Config.OVERPASS_FALLBACK_URLS", "https://two.invalid/api"),              mock.patch("app.services.store_locator_service.requests.post", return_value=self.reply()) as post:
            self.svc.fetch_overpass("q")
        self.assertEqual([c.args[0] for c in post.call_args_list], ["https://one.invalid/api"])

    def test_when_every_server_fails_the_last_failure_is_reported_not_an_empty_list(self):
        replies = [self.reply(504), self.reply(500)]
        with mock.patch("app.config.Config.OVERPASS_URL", "https://one.invalid/api"), mock.patch("app.config.Config.OVERPASS_FALLBACK_URLS", "https://two.invalid/api"),              mock.patch("app.services.store_locator_service.requests.post", side_effect=replies):
            with self.assertRaises(self.svc.PlacesUnavailable) as caught:
                self.svc.fetch_overpass("q")
        self.assertIn("returned an error", str(caught.exception))

    def test_the_server_list_has_no_blanks_or_repeats(self):
        with mock.patch("app.config.Config.OVERPASS_URL", "https://one.invalid/api"),              mock.patch("app.config.Config.OVERPASS_FALLBACK_URLS", " https://two.invalid/api , ,https://one.invalid/api,"):
            self.assertEqual(self.svc.overpass_urls(), ["https://one.invalid/api", "https://two.invalid/api"])

    def test_it_stops_trying_servers_once_the_time_budget_is_spent(self):
        clock = iter([0, 1, 100, 101, 102])
        with mock.patch("app.config.Config.OVERPASS_URL", "https://one.invalid/api"), mock.patch("app.config.Config.OVERPASS_FALLBACK_URLS", "https://two.invalid/api,https://three.invalid/api"),              mock.patch("app.services.store_locator_service.time.monotonic", side_effect=lambda: next(clock)),              mock.patch("app.services.store_locator_service.requests.post", return_value=self.reply(504)) as post:
            with self.assertRaises(self.svc.PlacesUnavailable):
                self.svc.fetch_overpass("q")
        self.assertEqual(post.call_count, 2, "the third server is not tried after the budget is gone")

    def test_a_server_that_is_switched_off_says_it_is_not_set_up(self):
        with mock.patch("app.config.Config.PLACES_PROVIDER", "off"), mock.patch("app.services.store_locator_service.requests.post") as post:
            with self.assertRaises(self.svc.PlacesNotConfigured) as caught:
                self.svc.fetch_overpass("q")
            with self.assertRaises(self.svc.PlacesNotConfigured):
                self.svc.geocode("Connaught Place")
        post.assert_not_called()
        self.assertIn("STORE_FINDER_SETUP", str(caught.exception))

    def test_search_returns_the_listed_stores_with_the_notices_a_reader_needs(self):
        out = self.svc.search_nearby("28.61391", "77.20908", 5, "generic", fetch=lambda q: {"elements": SAMPLE})
        self.assertEqual(out["center"], {"lat": 28.614, "lon": 77.209})
        self.assertEqual([s["store_id"] for s in out["stores"]], ["osm:node/1", "osm:node/2", "osm:way/4"])
        self.assertIn("OpenStreetMap contributors", out["attribution"])
        self.assertIn("has not verified them", out["verification_note"])
        self.assertIn("not stored", out["location_note"])
        self.assertEqual(out["official_locator_url"], "https://janaushadhi.gov.in/locate-kendra")

    def test_stores_beyond_the_radius_are_left_out(self):
        out = self.svc.search_nearby(28.614, 77.209, 1, "generic", fetch=lambda q: {"elements": SAMPLE})
        self.assertEqual([s["store_id"] for s in out["stores"]], ["osm:node/1"])

    def test_a_full_reply_is_flagged_as_possibly_incomplete(self):
        with mock.patch("app.config.Config.STORE_FETCH_LIMIT", 2):
            out = self.svc.search_nearby(28.614, 77.209, 5, "all", fetch=lambda q: {"elements": SAMPLE[:2]})
        self.assertTrue(out["may_be_incomplete"])
        self.assertFalse(self.svc.search_nearby(28.614, 77.209, 5, "all", fetch=lambda q: {"elements": SAMPLE[:2]})["may_be_incomplete"])

    def test_a_bad_scope_or_position_is_refused_before_any_request(self):
        fetch = mock.Mock()
        for kwargs in ({"lat": 1, "lon": 1, "scope": "everything"}, {"lat": "x", "lon": 1}, {"lat": 1, "lon": 1, "radius_km": "far"}):
            with self.assertRaises(ValueError):
                self.svc.search_nearby(fetch=fetch, **kwargs)
        fetch.assert_not_called()

    def test_the_same_area_is_not_asked_for_twice_within_the_cache_window(self):
        fetch = mock.Mock(return_value={"elements": SAMPLE})
        for _ in range(3):
            self.svc.search_nearby(28.61391, 77.20912, 5, "generic", fetch=fetch)          # rounds to the same place
        self.assertEqual(fetch.call_count, 1)
        self.svc.search_nearby(28.7, 77.3, 5, "generic", fetch=fetch)
        self.assertEqual(fetch.call_count, 2)

    def test_a_failure_is_not_cached(self):
        fetch = mock.Mock(side_effect=[self.svc.PlacesUnavailable("busy"), {"elements": SAMPLE}])
        with self.assertRaises(self.svc.PlacesUnavailable):
            self.svc.search_nearby(28.614, 77.209, 5, "generic", fetch=fetch)
        self.assertEqual(self.svc.search_nearby(28.614, 77.209, 5, "generic", fetch=fetch)["count"], 3)

    def test_place_search_returns_rounded_positions_and_drops_unusable_rows(self):
        found = [{"display_name": "Connaught Place, New Delhi", "lat": "28.63140", "lon": "77.21670"}, {"display_name": "", "lat": "1", "lon": "1"},
                 {"display_name": "Broken", "lat": "x", "lon": "1"}, {"display_name": "No position"}]
        out = self.svc.geocode("  Connaught   Place ", fetch=lambda q: found)
        self.assertEqual(out["query"], "Connaught Place")
        self.assertEqual(out["places"], [{"label": "Connaught Place, New Delhi", "lat": 28.631, "lon": 77.217}])

    def test_place_search_needs_a_sensible_query(self):
        for bad in (None, "", "ab", "x" * 101, "   "):
            with self.assertRaises(ValueError):
                self.svc.geocode(bad, fetch=lambda q: [])

    def test_place_search_failures_are_reported(self):
        with mock.patch("app.services.store_locator_service.requests.get", side_effect=requests.Timeout("slow")), \
             mock.patch("app.services.store_locator_service.time.sleep"):
            with self.assertRaises(self.svc.PlacesUnavailable):
                self.svc.geocode("Somewhere far away")


class ThroughTheRoutes(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.client = self.app.test_client()
        self.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        from app.services import store_locator_service
        self.svc = store_locator_service
        self.svc.clear_cache()
        with self.app.app_context():
            self.uid = self.accounts.user(allergies=[])
            self.h = {"Authorization": f"Bearer {create_access_token(identity=str(self.uid))}"}

    def tearDown(self):
        self.svc.clear_cache()
        with self.app.app_context():
            self.accounts.cleanup()

    def post(self, path, body=None, headers=True):
        return self.client.post(path, json=body, headers=self.h if headers else {})

    def patched(self, elements=None):
        return mock.patch("app.services.store_locator_service.fetch_overpass", return_value={"elements": SAMPLE if elements is None else elements})

    def test_both_routes_need_a_login(self):
        self.assertEqual(self.post("/api/stores/nearby", {"lat": 28.6, "lon": 77.2}, headers=False).status_code, 401)
        self.assertEqual(self.post("/api/stores/geocode", {"q": "Delhi"}, headers=False).status_code, 401)

    def test_a_position_in_the_url_is_not_accepted(self):
        self.assertEqual(self.client.get("/api/stores/nearby?lat=28.6&lon=77.2", headers=self.h).status_code, 405)
        self.assertEqual(self.client.get("/api/stores/geocode?q=Delhi", headers=self.h).status_code, 405)

    def test_nearby_returns_the_stores(self):
        with self.patched():
            r = self.post("/api/stores/nearby", {"lat": 28.61391, "lon": 77.20908, "radius_km": 5})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual([s["store_id"] for s in body["stores"]], ["osm:node/3", "osm:node/5", "osm:node/1", "osm:node/2", "osm:way/4"])      # every store, nearest first
        self.assertEqual(body["center"], {"lat": 28.614, "lon": 77.209})

    def test_bad_requests_get_a_clear_400(self):
        for body in (None, {}, {"lat": 28.6}, {"lat": "abc", "lon": 77}, {"lat": 95, "lon": 77}, {"lat": 28.6, "lon": 77, "scope": "nope"},
                     {"lat": 28.6, "lon": 77, "radius_km": "far"}, [1, 2], {"lat": [1], "lon": {}}):
            r = self.post("/api/stores/nearby", body)
            self.assertEqual(r.status_code, 400, body)
            self.assertIn("error", r.get_json())

    def test_the_default_shows_every_medical_store_and_kendra_and_the_filter_narrows_it(self):
        with self.patched():
            everything = self.post("/api/stores/nearby", {"lat": 28.614, "lon": 77.209, "radius_km": 5}).get_json()
            kendras = self.post("/api/stores/nearby", {"lat": 28.614, "lon": 77.209, "radius_km": 5, "scope": "generic"}).get_json()
        self.assertEqual((everything["scope"], kendras["scope"]), ("all", "generic"))
        self.assertEqual({s["store_id"] for s in everything["stores"]}, {"osm:node/1", "osm:node/2", "osm:node/3", "osm:way/4", "osm:node/5"})
        self.assertEqual({s["store_id"] for s in kendras["stores"]}, {"osm:node/1", "osm:node/2", "osm:way/4"})

    def test_distance_filters_narrow_the_list_through_the_route(self):
        with self.patched():
            counts = {km: self.post("/api/stores/nearby", {"lat": 28.614, "lon": 77.209, "radius_km": km}).get_json()["count"] for km in (0.5, 2, 5, 10)}
        self.assertEqual(counts, {0.5: 3, 2: 4, 5: 5, 10: 5})           # sample stores sit at 15, 30, 148, 1264 and 2714 m
        self.assertTrue(counts[0.5] <= counts[2] <= counts[5] <= counts[10])

    def test_an_empty_area_answers_with_no_stores_and_no_error(self):
        with self.patched(elements=[]):
            r = self.post("/api/stores/nearby", {"lat": 28.6, "lon": 77.2})
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.get_json()["count"], r.get_json()["stores"]), (0, []))

    def test_the_stores_answer_carries_no_medicine_stock_or_price_data_and_ignores_a_medicine_asked_for(self):
        with self.patched():
            plain = self.post("/api/stores/nearby", {"lat": 28.614, "lon": 77.209}).get_json()
            asked = self.post("/api/stores/nearby", {"lat": 28.614, "lon": 77.209, "medicine_id": 58235, "medicine_name": "Dolo 650"}).get_json()
        self.assertEqual(plain, asked)                                      # a medicine in the request changes nothing
        text = repr(plain).lower()
        for word in ("stock", "medicine_id", "price", "prescription", "availability", "offer"):
            self.assertNotIn(word, text, word)
        for store in plain["stores"]:
            self.assertEqual(set(store), {"store_id", "name", "category", "category_label", "address", "lat", "lon", "distance_m", "distance_text",
                                          "phone", "phone_link", "website", "opening_hours", "directions_url", "source", "listing_last_edited", "verified",
                                          "name_listed", "address_level", "address_parts", "listing_old", "also_listed_as"})

    def test_when_the_service_is_down_the_answer_is_an_error_not_an_empty_list(self):
        with mock.patch("app.services.store_locator_service.fetch_overpass", side_effect=self.svc.PlacesUnavailable("The store listing service is busy right now.")):
            r = self.post("/api/stores/nearby", {"lat": 28.6, "lon": 77.2})
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("stores", r.get_json())
        self.assertIn("busy", r.get_json()["error"])

    def test_when_the_provider_is_off_the_answer_says_it_is_not_configured(self):
        with mock.patch("app.config.Config.PLACES_PROVIDER", "off"):
            r = self.post("/api/stores/nearby", {"lat": 28.6, "lon": 77.2})
            g = self.post("/api/stores/geocode", {"q": "Delhi"})
        for resp in (r, g):
            self.assertEqual(resp.status_code, 503)
            self.assertIs(resp.get_json()["configured"], False)

    def test_geocode_route(self):
        with mock.patch("app.services.store_locator_service.requests.get") as get:
            get.return_value = mock.Mock(status_code=200, json=lambda: [{"display_name": "Connaught Place, New Delhi", "lat": "28.6317", "lon": "77.2167"}])
            with mock.patch("app.services.store_locator_service.time.sleep"):
                r = self.post("/api/stores/geocode", {"q": "Connaught Place"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["places"][0]["lat"], 28.632)
        self.assertEqual(self.post("/api/stores/geocode", {"q": "ab"}).status_code, 400)
        self.assertEqual(self.post("/api/stores/geocode").status_code, 400)

    def test_the_position_is_not_logged_and_nothing_is_stored(self):
        from app.db import get_connection

        def counts():
            conn = get_connection()
            cur = conn.cursor()
            out = []
            for table in ("System_Logs", "Prescriptions", "Pharmacy_Offers", "Pharmacies"):
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                out.append(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM System_Logs WHERE details LIKE %s", ("%28.61391%",))
            out.append(cur.fetchone()[0])
            cur.close()
            conn.close()
            return out

        with self.app.app_context():
            before = counts()
        import logging
        stream_records = []

        class Catch(logging.Handler):
            def emit(self, record):
                stream_records.append(record.getMessage())

        handler = Catch(level=logging.DEBUG)
        root = logging.getLogger()
        old_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            with self.patched():
                self.assertEqual(self.post("/api/stores/nearby", {"lat": 28.61391, "lon": 77.20908}).status_code, 200)
        finally:
            root.removeHandler(handler)
            root.setLevel(old_level)
        with self.app.app_context():
            self.assertEqual(counts(), before)
        self.assertFalse([m for m in stream_records if "28.61391" in m or "77.20908" in m], stream_records)


class Independence(unittest.TestCase):
    """The Stores feature touches none of the medicine, price, availability or recommendation code, and none of it touches the stores."""

    BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def source(self, *parts):
        with open(os.path.join(self.BACKEND, *parts), encoding="utf8") as handle:
            return handle.read()

    def test_the_store_code_imports_nothing_about_medicines_prescriptions_prices_or_stock(self):
        for path in (("app", "services", "store_locator_service.py"), ("app", "routes", "stores.py")):
            imports = " ".join(re.findall(r"^\s*(?:from|import)\s+([\w.]+)", self.source(*path), re.MULTILINE))
            for forbidden in ("medicine", "prescription", "offer", "price", "recommend", "safety", "match", "composition", "availability"):
                self.assertNotIn(forbidden, imports, f"{path[-1]} imports {forbidden}")

    def test_no_other_part_of_the_project_uses_the_store_code(self):
        users = []
        for folder, _dirs, files in os.walk(os.path.join(self.BACKEND, "app")):
            for name in files:
                if name.endswith(".py") and name not in ("store_locator_service.py", "stores.py"):
                    with open(os.path.join(folder, name), encoding="utf8") as handle:
                        text = handle.read()
                    if "store_locator" in text or "routes.stores" in text:
                        users.append(name)
        self.assertEqual(users, ["__init__.py"], "only the app factory registers the stores blueprint")

    def test_the_offers_importer_and_schema_know_nothing_about_stores(self):
        for path in (("app", "models", "offer_model.py"), ("app", "services", "feed_import_service.py"), ("database", "schema.sql")):
            self.assertNotIn("place_ref", self.source(*path))


if __name__ == "__main__":
    unittest.main()
