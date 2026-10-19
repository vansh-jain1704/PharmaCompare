"""
The Stores page's listing quality: the names, addresses, duplicate handling, filters and age of the OpenStreetMap entries it shows.

The entries here are SMALL SAMPLES WRITTEN FOR THE TESTS in OpenStreetMap's format: no store in them exists, and no request leaves this machine.
Some mirror what a real search showed (shops a few metres apart with different phone numbers, entries with no name), because those cases decide
the rules. What is proved: a name is only ever one the listing carries; an address is only what the listing says; two entries merge only on
evidence and never because they are close; every filter keeps what it says; and an old or incomplete listing is said to be so.
"""
import unittest
from datetime import date
from unittest import mock

from tests import helpers
from tests.test_store_locator import SAMPLE, node

ORIGIN = (28.614, 77.209)
TODAY = date(2026, 10, 18)


def entry(osm_id, name, lat=28.6150, lon=77.2100, kind="node", **tags):
    """A pharmacy entry. `kind` way gives a building outline (position as a centre)."""
    base = {"amenity": "pharmacy", **({"name": name} if name else {})}
    base.update(tags)
    if kind == "node":
        return {"type": "node", "id": osm_id, "lat": lat, "lon": lon, "timestamp": "2026-05-01T10:00:00Z", "tags": base}
    return {"type": kind, "id": osm_id, "center": {"lat": lat, "lon": lon}, "timestamp": "2026-05-01T10:00:00Z", "tags": base}


def metres_north(lat, metres):
    return lat + metres / 111195.0


class Names(unittest.TestCase):
    def setUp(self):
        from app.services import store_locator_service
        self.svc = store_locator_service

    def test_the_listings_own_name_is_shown(self):
        self.assertEqual(self.svc.store_name({"name": "Manjula Medicals"}), "Manjula Medicals")

    def test_the_order_of_names_tried(self):
        self.assertEqual(self.svc.store_name({"name": "A", "name:en": "B", "brand": "C"}), "A")
        self.assertEqual(self.svc.store_name({"name:en": "B", "official_name": "O", "brand": "C"}), "B")
        self.assertEqual(self.svc.store_name({"official_name": "O", "brand": "C"}), "O")
        self.assertEqual(self.svc.store_name({"brand": "Jan Aushadhi", "operator": "X"}), "Jan Aushadhi")
        self.assertEqual(self.svc.store_name({"name:kn": "ಔಷಧ", "name:hi": "z"}), "z", "other-language names in a fixed order, only when nothing else is listed")

    def test_no_name_is_never_replaced_by_something_that_looks_like_one(self):
        for tags in ({}, {"amenity": "pharmacy"}, {"name": "  "}, {"name": "\n\t"}, {"operator": "Some Trust"}, {"description": "next to the bank"}, {"addr:street": "Hadadi Road"}):
            self.assertIsNone(self.svc.store_name(tags), tags)

    def test_an_unnamed_entry_says_so_in_the_stated_words(self):
        got = self.svc.parse_elements([entry(1, None)], ORIGIN, "all")
        self.assertEqual((got[0]["name"], got[0]["name_listed"]), ("Pharmacy — name unavailable", False))
        named = self.svc.parse_elements([entry(2, "Manjula Medicals")], ORIGIN, "all")
        self.assertEqual((named[0]["name"], named[0]["name_listed"]), ("Manjula Medicals", True))

    def test_a_name_is_one_clean_line_and_bounded(self):
        got = self.svc.parse_elements([entry(1, "  Shree \n  Medicals\t")], ORIGIN, "all")
        self.assertEqual(got[0]["name"], "Shree Medicals")
        self.assertEqual(len(self.svc.store_name({"name": "x" * 400})), 150)

    def test_an_unnamed_kendra_listed_by_brand_is_named_and_classed_by_that_brand(self):
        got = self.svc.parse_elements([entry(1, None, brand="Pradhan Mantri Bhartiya Janaushadhi Kendra")], ORIGIN, "all")
        self.assertEqual((got[0]["name"], got[0]["category"]), ("Pradhan Mantri Bhartiya Janaushadhi Kendra", "jan_aushadhi"))


class Addresses(unittest.TestCase):
    def setUp(self):
        from app.services import store_locator_service
        self.addr = store_locator_service.address_parts

    def test_a_complete_address_has_street_locality_town_and_pin(self):
        a = self.addr({"addr:housenumber": "12", "addr:street": "Test Road", "addr:suburb": "Old Town", "addr:city": "Testville", "addr:postcode": "110001"})
        self.assertEqual(a["text"], "12 Test Road, Old Town, Testville, 110001")
        self.assertEqual((a["street"], a["locality"], a["town"], a["postcode"], a["level"]), ("12 Test Road", "Old Town", "Testville", "110001", "full"))

    def test_what_is_missing_makes_it_partial_and_nothing_is_added(self):
        for tags, text in (
            ({"addr:city": "Davanagere", "addr:postcode": "577004"}, "Davanagere, 577004"),
            ({"addr:street": "Hadadi Road"}, "Hadadi Road"),
            ({"addr:postcode": "577002"}, "577002"),
            ({"addr:housenumber": "8", "addr:city": "New Delhi"}, "8, New Delhi"),
        ):
            a = self.addr(tags)
            self.assertEqual((a["text"], a["level"]), (text, "partial"), tags)

    def test_a_house_number_alone_is_not_a_street(self):
        a = self.addr({"addr:housenumber": "7", "addr:city": "New Delhi", "addr:postcode": "110001"})
        self.assertEqual(a["level"], "partial")

    def test_no_address_tags_means_none_listed(self):
        for tags in ({}, {"name": "X", "phone": "123456"}, {"addr:street": "  "}, {"addr:city": ""}):
            a = self.addr(tags)
            self.assertEqual((a["text"], a["level"]), (None, "none"), tags)

    def test_a_bare_block_letter_is_labelled_a_block(self):
        self.assertEqual(self.addr({"addr:block": "G", "addr:city": "New Delhi"})["text"], "Block G, New Delhi")
        self.assertEqual(self.addr({"addr:block": "Block A", "addr:city": "New Delhi"})["text"], "Block A, New Delhi")

    def test_the_other_listed_parts_are_used(self):
        a = self.addr({"addr:housename": "Marina Arcade", "addr:place": "Connaught Circus", "addr:hamlet": "Ward 4", "addr:subdistrict": "Taluku",
                       "addr:district": "Central", "addr:state": "Delhi", "addr:city": "New Delhi", "addr:postcode": "110001"})
        self.assertEqual(a["text"], "Marina Arcade, Connaught Circus, Ward 4, Taluku, New Delhi, Central, Delhi, 110001")
        self.assertEqual(a["level"], "full")

    def test_a_repeated_place_is_said_once(self):
        self.assertEqual(self.addr({"addr:city": "Davanagere", "addr:district": "davanagere", "addr:postcode": "577001"})["text"], "Davanagere, 577001")

    def test_pin_codes_are_tidied_only_when_they_are_pin_codes(self):
        self.assertEqual(self.addr({"addr:postcode": "577 002"})["postcode"], "577002")
        self.assertEqual(self.addr({"addr:postcode": " 110001 "})["postcode"], "110001")
        self.assertEqual(self.addr({"addr:postcode": "12345"})["postcode"], "12345", "not six digits: shown as written, not repaired")
        self.assertEqual(self.addr({"addr:postcode": "ABC 12"})["postcode"], "ABC 12")

    def test_a_full_address_line_is_used_as_given(self):
        a = self.addr({"addr:full": "  Shop 4, Some Complex,\n Town 560001 ", "addr:city": "Ignored"})
        self.assertEqual((a["text"], a["level"]), ("Shop 4, Some Complex, Town 560001", "full"))

    def test_control_characters_never_reach_an_address(self):
        a = self.addr({"addr:street": "Main\u0000 Road\x07", "addr:city": "Town\n"})
        self.assertNotRegex(a["text"], r"[\x00-\x1f]")

    def test_the_store_carries_the_level_and_parts(self):
        from app.services import store_locator_service as svc
        got = svc.parse_elements([entry(1, "X", **{"addr:street": "Hadadi Road", "addr:city": "Davanagere", "addr:postcode": "577002"})], ORIGIN, "all")[0]
        self.assertEqual((got["address"], got["address_level"]), ("Hadadi Road, Davanagere, 577002", "full"))
        self.assertEqual(got["address_parts"], {"street": "Hadadi Road", "locality": None, "town": "Davanagere", "postcode": "577002"})
        none = svc.parse_elements([entry(2, "Y")], ORIGIN, "all")[0]
        self.assertEqual((none["address"], none["address_level"]), (None, "none"))


class Duplicates(unittest.TestCase):
    def setUp(self):
        from app.services import store_locator_service
        self.svc = store_locator_service

    def parse(self, *elements, scope="all"):
        return self.svc.parse_elements(list(elements), ORIGIN, scope, today=TODAY)

    def test_a_point_and_a_building_outline_with_the_same_name_close_together_are_one_store(self):
        got = self.parse(entry(1, "Manjula Medicals", lat=28.6150, lon=77.2100, phone="+91 11 2345 6789"),
                         entry(2, "Manjula Medicals", lat=metres_north(28.6150, 40), lon=77.2100, kind="way"))
        self.assertEqual(len(got), 1)
        self.assertEqual(len(got[0]["also_listed_as"]), 1)
        other = got[0]["also_listed_as"][0]
        self.assertEqual(other["store_id"], "osm:way/2")
        self.assertIn("the same name", other["reason"])
        self.assertIn("nothing that differs", other["reason"])
        self.assertTrue(38 <= other["metres_apart"] <= 42)

    def test_two_points_with_the_same_name_merge_only_within_25_metres(self):
        close = self.parse(entry(1, "Apollo Pharmacy"), entry(2, "Apollo Pharmacy", lat=metres_north(28.6150, 20)))
        self.assertEqual(len(close), 1)
        apart = self.parse(entry(1, "Apollo Pharmacy"), entry(2, "Apollo Pharmacy", lat=metres_north(28.6150, 30)))
        self.assertEqual(len(apart), 2, "30 m between two points is two shops: chains do open next to each other")

    def test_a_point_and_an_outline_merge_only_within_60_metres(self):
        self.assertEqual(len(self.parse(entry(1, "X Medicals"), entry(2, "X Medicals", lat=metres_north(28.6150, 55), kind="way"))), 1)
        self.assertEqual(len(self.parse(entry(1, "X Medicals"), entry(2, "X Medicals", lat=metres_north(28.6150, 70), kind="way"))), 2)

    def test_shops_a_few_metres_apart_with_different_names_are_never_merged(self):
        got = self.parse(entry(1, "Medicine House", phone="+91-95825-34440"), entry(2, "Nath Brothers", lat=metres_north(28.6150, 4), phone="+91-98994-41605"),
                         entry(3, "Arora AG & Medical Store", lat=metres_north(28.6150, 6)))
        self.assertEqual(len(got), 3)
        self.assertTrue(all(s["also_listed_as"] == [] for s in got))

    def test_entries_without_a_name_are_never_merged_however_alike_they_look(self):
        twins = [entry(i, None, lat=metres_north(28.6150, i), **{"healthcare": "pharmacy", "dispensing": "yes"}) for i in (1, 2, 3)]
        got = self.parse(*twins)
        self.assertEqual(len(got), 3, "no name means nothing says they are one shop")
        self.assertTrue(all(not s["name_listed"] and s["also_listed_as"] == [] for s in got))

    def test_an_unnamed_entry_is_not_merged_into_a_named_one_beside_it(self):
        got = self.parse(entry(1, "Manjula Medicals"), entry(2, None, lat=metres_north(28.6150, 5)))
        self.assertEqual(len(got), 2)

    def test_the_same_name_with_a_different_phone_number_is_a_different_shop(self):
        got = self.parse(entry(1, "Apollo Pharmacy", phone="+91 80 2286 8423"), entry(2, "Apollo Pharmacy", lat=metres_north(28.6150, 10), phone="080 4000 1111"))
        self.assertEqual(len(got), 2)

    def test_the_same_phone_written_differently_is_still_the_same_phone(self):
        got = self.parse(entry(1, "Apollo Pharmacy", phone="+91 80 2286 8423"), entry(2, "Apollo Pharmacy", lat=metres_north(28.6150, 10), phone="080-2286-8423"))
        self.assertEqual(len(got), 1)
        self.assertIn("the same phone number", got[0]["also_listed_as"][0]["reason"])

    def test_one_listing_with_a_phone_and_one_without_can_still_be_the_same_shop(self):
        got = self.parse(entry(1, "Apollo Pharmacy", phone="+91 80 2286 8423"), entry(2, "Apollo Pharmacy", lat=metres_north(28.6150, 10)))
        self.assertEqual(len(got), 1)

    def test_anything_that_contradicts_keeps_them_apart(self):
        for tags_a, tags_b in (
            ({"addr:housenumber": "12"}, {"addr:housenumber": "14"}),
            ({"addr:street": "Hadadi Road"}, {"addr:street": "Station Road"}),
            ({"addr:postcode": "577002"}, {"addr:postcode": "577004"}),
            ({"branch": "North"}, {"branch": "South"}),
            ({"ref": "A-12"}, {"ref": "A-13"}),
        ):
            got = self.parse(entry(1, "Apollo Pharmacy", **tags_a), entry(2, "Apollo Pharmacy", lat=metres_north(28.6150, 5), **tags_b))
            self.assertEqual(len(got), 2, (tags_a, tags_b))
        same = self.parse(entry(1, "Apollo Pharmacy", **{"addr:street": "Hadadi Road"}), entry(2, "Apollo Pharmacy", lat=metres_north(28.6150, 5), **{"addr:street": "hadadi  road"}))
        self.assertEqual(len(same), 1, "the same street written another way does not contradict")

    def test_names_are_compared_ignoring_case_and_punctuation_only(self):
        got = self.parse(entry(1, "Apollo Pharmacy"), entry(2, "APOLLO  PHARMACY."))
        self.assertEqual(len(got), 1)
        different = self.parse(entry(1, "Sundeep Medical Shop"), entry(2, "Sundeep Medicals", lat=metres_north(28.6150, 5)))
        self.assertEqual(len(different), 2, "similar is not the same: spellings are not guessed at")

    def test_the_same_name_far_apart_is_two_stores(self):
        got = self.parse(entry(1, "Apollo Pharmacy"), entry(2, "Apollo Pharmacy", lat=metres_north(28.6150, 500)))
        self.assertEqual(len(got), 2)

    def test_the_entry_that_says_most_is_kept_and_nothing_is_copied_from_the_other(self):
        poor = entry(1, "Manjula Medicals", lat=28.6150)
        rich = entry(2, "Manjula Medicals", lat=metres_north(28.6150, 10), phone="+91 11 2345 6789", opening_hours="Mo-Sa 09:00-21:00", **{"addr:street": "Hadadi Road"})
        got = self.parse(poor, rich)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["store_id"], "osm:node/2")
        self.assertEqual(got[0]["phone"], "+91 11 2345 6789")
        got_poor_first = self.parse(rich, poor)
        self.assertEqual(got_poor_first[0]["store_id"], "osm:node/2", "the order of the reply does not decide")
        poor_only = self.parse(poor)
        self.assertIsNone(poor_only[0]["phone"])
        merged_away = self.parse(entry(1, "Manjula Medicals", phone="+91 11 2345 6789"), entry(2, "Manjula Medicals", lat=metres_north(28.6150, 10), **{"addr:street": "Hadadi Road", "addr:city": "T", "addr:postcode": "577002", "website": "https://example.invalid"}))
        kept = merged_away[0]
        self.assertEqual(kept["store_id"], "osm:node/2")
        self.assertIsNone(kept["phone"], "the dropped entry's phone is not attached to the kept one")

    def test_when_they_say_the_same_a_point_beats_an_outline_and_then_the_newer_edit_wins(self):
        point = entry(5, "X Medicals")
        outline = entry(1, "X Medicals", lat=metres_north(28.6150, 20), kind="way")
        self.assertEqual(self.parse(point, outline)[0]["store_id"], "osm:node/5")
        old, new = entry(7, "Y Medicals"), entry(8, "Y Medicals", lat=metres_north(28.6150, 10))
        old["timestamp"] = "2019-01-01T00:00:00Z"
        self.assertEqual(self.parse(old, new)[0]["store_id"], "osm:node/8")

    def test_three_entries_for_one_shop_become_one_naming_the_other_two(self):
        got = self.parse(entry(1, "Z Pharmacy"), entry(2, "Z Pharmacy", lat=metres_north(28.6150, 10)), entry(3, "Z Pharmacy", lat=metres_north(28.6150, 15), kind="way"))
        self.assertEqual(len(got), 1)
        self.assertEqual(sorted(a["store_id"] for a in got[0]["also_listed_as"]), sorted({"osm:node/1", "osm:node/2", "osm:way/3"} - {got[0]["store_id"]}))

    def test_the_same_element_twice_is_one_entry(self):
        got = self.parse(entry(1, "Same"), entry(1, "Same"))
        self.assertEqual((len(got), got[0]["also_listed_as"]), (1, []))

    def test_a_node_and_a_way_with_the_same_number_are_different_elements(self):
        got = self.parse(entry(9, "Alpha Medicals"), entry(9, "Beta Medicals", lat=metres_north(28.6150, 300), kind="way"))
        self.assertEqual(sorted(s["store_id"] for s in got), ["osm:node/9", "osm:way/9"])

    def test_a_merged_store_keeps_its_own_position_and_distance(self):
        got = self.parse(entry(1, "Manjula Medicals", lat=28.6150), entry(2, "Manjula Medicals", lat=metres_north(28.6150, 40), kind="way"))
        self.assertEqual(got[0]["lat"], 28.615)
        self.assertEqual(got[0]["distance_m"], self.svc.parse_elements([entry(1, "Manjula Medicals")], ORIGIN, "all")[0]["distance_m"])

    def test_the_search_says_how_many_duplicates_it_folded_in(self):
        elements = [entry(1, "Manjula Medicals"), entry(2, "Manjula Medicals", lat=metres_north(28.6150, 10)), entry(3, "Other Chemists", lat=metres_north(28.6150, 300))]
        out = self.svc.search_nearby(28.614, 77.209, 5, "all", fetch=lambda q: {"elements": elements})
        self.svc.clear_cache()
        self.assertEqual((out["count"], out["duplicates_merged"]), (2, 1))


class Filters(unittest.TestCase):
    def setUp(self):
        from app.services import store_locator_service
        self.svc = store_locator_service

    def ids(self, scope):
        return {s["store_id"] for s in self.svc.parse_elements(SAMPLE, ORIGIN, scope, today=TODAY)}

    def test_each_filter_keeps_what_it_says(self):
        self.assertEqual(self.ids("all"), {"osm:node/1", "osm:node/2", "osm:node/3", "osm:way/4", "osm:node/5"})
        self.assertEqual(self.ids("jan_aushadhi"), {"osm:node/1", "osm:way/4"})
        self.assertEqual(self.ids("generic"), {"osm:node/1", "osm:node/2", "osm:way/4"})
        self.assertEqual(self.ids("pharmacy"), {"osm:node/3", "osm:node/5"})

    def test_the_filters_never_overlap_wrongly(self):
        self.assertEqual(self.ids("jan_aushadhi") | self.ids("pharmacy") | {"osm:node/2"}, self.ids("all"))
        self.assertFalse(self.ids("jan_aushadhi") & self.ids("pharmacy"))

    def test_kendras_only_shows_only_kendras(self):
        for store in self.svc.parse_elements(SAMPLE, ORIGIN, "jan_aushadhi"):
            self.assertEqual(store["category"], "jan_aushadhi")

    def test_an_unknown_filter_is_refused_not_treated_as_all(self):
        with self.assertRaises(ValueError):
            self.svc.parse_elements(SAMPLE, ORIGIN, "everything")
        with self.assertRaises(ValueError):
            self.svc.search_nearby(28.614, 77.209, 5, "pharmacies", fetch=lambda q: {"elements": SAMPLE})

    def test_the_answer_counts_each_kind_so_the_map_key_can_match_the_list(self):
        out = self.svc.search_nearby(28.614, 77.209, 5, "all", fetch=lambda q: {"elements": SAMPLE})
        self.svc.clear_cache()
        self.assertEqual(out["category_counts"], {"jan_aushadhi": 2, "generic": 1, "pharmacy": 2})
        self.assertEqual(sum(out["category_counts"].values()), out["count"])
        only = self.svc.search_nearby(28.614, 77.209, 5, "jan_aushadhi", fetch=lambda q: {"elements": SAMPLE})
        self.svc.clear_cache()
        self.assertEqual((only["count"], only["category_counts"]), (2, {"jan_aushadhi": 2, "generic": 0, "pharmacy": 0}))

    def test_the_distance_filter_still_applies_with_every_category_filter(self):
        for scope in self.svc.SCOPES:
            out = self.svc.search_nearby(28.614, 77.209, 0.5, scope, fetch=lambda q: {"elements": SAMPLE})
            self.svc.clear_cache()
            self.assertTrue(all(s["distance_m"] <= 500 for s in out["stores"]), scope)


class WhenTheListIsCut(unittest.TestCase):
    """The page shows at most STORE_MAX_RESULTS stores; when there are more, the answer says how many there were."""

    def setUp(self):
        from app.services import store_locator_service
        self.svc = store_locator_service
        self.svc.clear_cache()
        self.addCleanup(self.svc.clear_cache)
        self.elements = [entry(i, f"Chemist {i}", lat=metres_north(28.6140, 100 * i)) for i in range(1, 8)]

    def search(self, limit):
        with mock.patch("app.config.Config.STORE_MAX_RESULTS", limit):
            self.svc.clear_cache()
            return self.svc.search_nearby(28.614, 77.209, 5, "all", fetch=lambda q: {"elements": self.elements})

    def test_a_cut_list_says_how_many_there_were_and_shows_the_nearest(self):
        out = self.search(3)
        self.assertEqual((out["count"], out["total_found"]), (3, 7))
        self.assertEqual([s["name"] for s in out["stores"]], ["Chemist 1", "Chemist 2", "Chemist 3"])
        self.assertEqual(sum(out["category_counts"].values()), 3, "the key counts what is shown")

    def test_a_list_that_fits_is_not_called_cut(self):
        out = self.search(30)
        self.assertEqual((out["count"], out["total_found"]), (7, 7))

    def test_the_total_follows_the_distance_filter_and_the_category_filter(self):
        with mock.patch("app.config.Config.STORE_MAX_RESULTS", 2):
            self.svc.clear_cache()
            near = self.svc.search_nearby(28.614, 77.209, 0.5, "all", fetch=lambda q: {"elements": self.elements})
            self.svc.clear_cache()
            kendras = self.svc.search_nearby(28.614, 77.209, 5, "jan_aushadhi", fetch=lambda q: {"elements": self.elements})
        self.assertEqual((near["count"], near["total_found"]), (2, 4), "four are within 500 m")
        self.assertEqual((kendras["count"], kendras["total_found"]), (0, 0))

    def test_merged_duplicates_are_counted_once_in_the_total(self):
        twins = [entry(1, "Twin Medicals"), entry(2, "Twin Medicals", lat=metres_north(28.6150, 10)), entry(3, "Other Chemist", lat=metres_north(28.6150, 300))]
        self.svc.clear_cache()
        out = self.svc.search_nearby(28.614, 77.209, 5, "all", fetch=lambda q: {"elements": twins})
        self.assertEqual((out["count"], out["total_found"], out["duplicates_merged"]), (2, 2, 1))


class ListingAge(unittest.TestCase):
    def setUp(self):
        from app.services import store_locator_service
        self.svc = store_locator_service

    def old(self, stamp, today=TODAY):
        el = entry(1, "X")
        if stamp is None:
            el.pop("timestamp")
        else:
            el["timestamp"] = stamp
        return self.svc.parse_elements([el], ORIGIN, "all", today=today)[0]

    def test_a_listing_not_edited_for_three_years_is_called_old(self):
        self.assertTrue(self.old("2014-10-13T00:00:00Z")["listing_old"])
        self.assertTrue(self.old("2023-10-17T00:00:00Z")["listing_old"])
        self.assertFalse(self.old("2023-10-19T00:00:00Z")["listing_old"])
        self.assertFalse(self.old("2026-10-01T00:00:00Z")["listing_old"])

    def test_the_policy_is_a_setting(self):
        with mock.patch("app.config.Config.STORE_LISTING_OLD_DAYS", 30):
            self.assertTrue(self.old("2026-08-01T00:00:00Z")["listing_old"])
            self.assertFalse(self.old("2026-10-10T00:00:00Z")["listing_old"])

    def test_no_edit_date_is_not_called_old_or_new(self):
        got = self.old(None)
        self.assertIsNone(got["listing_last_edited"])
        self.assertFalse(got["listing_old"])
        self.assertFalse(self.old("garbage")["listing_old"])


class OnlyWhatIsListed(unittest.TestCase):
    def setUp(self):
        from app.services import store_locator_service
        self.svc = store_locator_service

    def test_phone_and_opening_hours_appear_only_when_the_listing_gives_them(self):
        bare = self.svc.parse_elements([entry(1, "Bare Medicals")], ORIGIN, "all")[0]
        self.assertEqual((bare["phone"], bare["phone_link"], bare["opening_hours"], bare["website"]), (None, None, None, None))
        full = self.svc.parse_elements([entry(2, "Full Medicals", phone="+91 80 2286 8423", opening_hours="Mo-Sa 09:00-21:00", website="https://example.invalid")], ORIGIN, "all")[0]
        self.assertEqual((full["phone"], full["opening_hours"], full["website"]), ("+91 80 2286 8423", "Mo-Sa 09:00-21:00", "https://example.invalid"))
        self.assertEqual(full["phone_link"], "tel:+918022868423")

    def test_the_warning_says_community_edited_incomplete_out_of_date_and_not_verified(self):
        note = self.svc.NOT_VERIFIED_NOTE
        for needle in ("OpenStreetMap", "volunteers", "has not verified them", "incomplete", "out of date", "moved or closed", "official Jan Aushadhi Kendra locator"):
            self.assertIn(needle, note)

    def test_the_answer_carries_the_warning_the_locator_link_and_the_attribution(self):
        out = self.svc.search_nearby(28.614, 77.209, 5, "all", fetch=lambda q: {"elements": SAMPLE})
        self.svc.clear_cache()
        self.assertEqual(out["verification_note"], self.svc.NOT_VERIFIED_NOTE)
        self.assertEqual(out["official_locator_url"], "https://janaushadhi.gov.in/locate-kendra")
        self.assertIn("OpenStreetMap contributors", out["attribution"])
        self.assertTrue(all(s["verified"] is False for s in out["stores"]))


class ThroughTheRoute(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.client = self.app.test_client()
        self.accounts = helpers.TempAccounts()
        from flask_jwt_extended import create_access_token
        from app.services import store_locator_service
        self.svc = store_locator_service
        self.svc.clear_cache()
        with self.app.app_context():
            uid = self.accounts.user(allergies=[])
            self.h = {"Authorization": f"Bearer {create_access_token(identity=str(uid))}"}

    def tearDown(self):
        self.svc.clear_cache()
        with self.app.app_context():
            self.accounts.cleanup()

    def post(self, body):
        with mock.patch("app.services.store_locator_service.fetch_overpass", return_value={"elements": SAMPLE}):
            return self.client.post("/api/stores/nearby", json=body, headers=self.h)

    def test_every_filter_works_through_the_route(self):
        expected = {"all": 5, "jan_aushadhi": 2, "generic": 3, "pharmacy": 2}
        for scope, count in expected.items():
            self.svc.clear_cache()
            r = self.post({"lat": 28.614, "lon": 77.209, "radius_km": 5, "scope": scope})
            self.assertEqual(r.status_code, 200, scope)
            self.assertEqual((r.get_json()["scope"], r.get_json()["count"]), (scope, count), scope)

    def test_a_bad_filter_is_a_400(self):
        r = self.post({"lat": 28.614, "lon": 77.209, "scope": "kendras"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("scope must be one of", r.get_json()["error"])

    def test_the_list_the_map_draws_from_is_the_list_shown(self):
        body = self.post({"lat": 28.614, "lon": 77.209, "radius_km": 5}).get_json()
        self.assertEqual(body["count"], len(body["stores"]))
        self.assertEqual(sum(body["category_counts"].values()), len(body["stores"]))
        self.assertEqual(len({s["store_id"] for s in body["stores"]}), len(body["stores"]), "no store twice")
        self.assertEqual([s["distance_m"] for s in body["stores"]], sorted(s["distance_m"] for s in body["stores"]))

    def test_provider_failure_and_empty_area_are_still_told_apart(self):
        with mock.patch("app.services.store_locator_service.fetch_overpass", side_effect=self.svc.PlacesUnavailable("The store listing service is busy right now.")):
            failed = self.client.post("/api/stores/nearby", json={"lat": 28.6, "lon": 77.2}, headers=self.h)
        self.assertEqual(failed.status_code, 503)
        self.assertNotIn("stores", failed.get_json())
        self.svc.clear_cache()
        with mock.patch("app.services.store_locator_service.fetch_overpass", return_value={"elements": []}):
            empty = self.client.post("/api/stores/nearby", json={"lat": 28.6, "lon": 77.2}, headers=self.h)
        self.assertEqual((empty.status_code, empty.get_json()["count"], empty.get_json()["stores"]), (200, 0, []))
        self.assertEqual(empty.get_json()["duplicates_merged"], 0)


if __name__ == "__main__":
    unittest.main()
