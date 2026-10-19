"""
Finding medical stores and Jan Aushadhi Kendras near a place.

This is an independent, location-only feature. It knows nothing about medicines, prescriptions, prices or stock: it never reads or writes
any of that data, and nothing here is connected to the medicine, price-comparison, availability or recommendation features.

Where the data comes from: OpenStreetMap, through an Overpass API server (Config.OVERPASS_URL, with fallbacks). OpenStreetMap is
community-maintained open data (ODbL licence, attribution required). That has two consequences this module keeps honest:

  - A store is only ever a store OpenStreetMap lists. Nothing is invented, estimated or filled in. A store with no phone has no phone.
  - Nothing here is "verified". A store is classed as a Jan Aushadhi Kendra or a generic store from the name / brand text it is listed
    under, which anyone can edit; the result says so, shows when the listing was last edited, and points to the official locator.

Privacy: the person's position is rounded to about 100 m before it is used for anything, it is not stored, and it is not logged.
Public Overpass servers are meant for light, human-operated use: results are cached briefly, and a production deployment should point
OVERPASS_URL at its own Overpass instance (see docs/STORE_FINDER_SETUP.md).
"""
import math
import re
import threading
import time
from collections import Counter, defaultdict
from datetime import date, datetime

import requests

from app.config import Config

# which kinds of store each filter keeps: all = everything; jan_aushadhi = Kendras only; generic = Kendras and generic stores; pharmacy = the others
SCOPE_CATEGORIES = {"all": None, "jan_aushadhi": {"jan_aushadhi"}, "generic": {"jan_aushadhi", "generic"}, "pharmacy": {"pharmacy"}}
SCOPES = tuple(SCOPE_CATEGORIES)
NAME_UNAVAILABLE = "Pharmacy \u2014 name unavailable"       # shown when the listing carries no name; a name is never made up
CATEGORY_LABELS = {"jan_aushadhi": "Jan Aushadhi Kendra", "generic": "Generic medicine store", "pharmacy": "Pharmacy"}
OFFICIAL_LOCATOR_URL = "https://janaushadhi.gov.in/locate-kendra"
ATTRIBUTION = "Store data © OpenStreetMap contributors (ODbL). Map tiles © OpenStreetMap contributors."
NOT_VERIFIED_NOTE = (
    "These stores come from OpenStreetMap, a map edited by volunteers. PharmaCompare has not verified them: a listing can be incomplete, out of date or "
    "missing, and a store may have moved or closed. Phone ahead or check the official Jan Aushadhi Kendra locator before travelling."
)

MIN_RADIUS_KM = 0.5
COORDINATE_DECIMALS = 3                      # about 110 m
EARTH_RADIUS_M = 6371008.8

_JAN_AUSHADHI = re.compile(r"\bjana?[\s\-]*aush?a?dh?i|जन[\s\-]*औषधि|pmbj[pk]|pmbi\b|bhartiya\s+jan", re.IGNORECASE)
_GENERIC = re.compile(r"generic|जेनेरिक", re.IGNORECASE)
_NAME_KEYS = ("name", "name:en", "name:hi", "brand", "brand:en", "operator", "alt_name")
_PHONE_OK = re.compile(r"^[0-9+()\s\-./;,]{5,60}$")


class PlacesUnavailable(Exception):
    """The place data could not be fetched. The message is safe to show to the person."""


class PlacesNotConfigured(PlacesUnavailable):
    """No usable provider is configured."""


# --- location handling ---------------------------------------------------------------------------------------------------------

def clean_coordinates(lat, lon):
    """(lat, lon) as floats rounded to about 100 m, or ValueError. Nothing finer than this is used, kept or sent on."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise ValueError("lat and lon must be numbers")
    if not (math.isfinite(lat) and math.isfinite(lon)) or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise ValueError("lat must be between -90 and 90 and lon between -180 and 180")
    return round(lat, COORDINATE_DECIMALS), round(lon, COORDINATE_DECIMALS)


def clean_radius_km(value):
    try:
        radius = float(value)
    except (TypeError, ValueError):
        raise ValueError("radius_km must be a number")
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("radius_km must be a positive number")
    return min(max(radius, MIN_RADIUS_KM), float(Config.STORE_MAX_RADIUS_KM))


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def distance_text(metres):
    if metres < 1000:
        return f"{int(round(metres, -1)) if metres >= 100 else int(round(metres))} m"
    return f"{metres / 1000:.1f} km"


def directions_url(lat, lon):
    """A plain link that opens turn-by-turn directions to the store from wherever the person is. No API key, nothing sent from here."""
    return f"https://www.google.com/maps/dir/?api=1&destination={lat:.6f},{lon:.6f}"


# --- reading OpenStreetMap elements --------------------------------------------------------------------------------------------

def classify(tags):
    """'jan_aushadhi', 'generic' or 'pharmacy' from the text the store is listed under; never a statement that it is official."""
    text = " ".join(str(tags.get(k, "")) for k in _NAME_KEYS)
    if _JAN_AUSHADHI.search(text):
        return "jan_aushadhi"
    if _GENERIC.search(text):
        return "generic"
    return "pharmacy"


def _text(value, limit=150):
    """A tag value as one clean line (control characters and runs of spaces flattened), or "" ."""
    return re.sub(r"\s+", " ", re.sub(r"[\u0000-\u001f\u007f]", " ", str(value or ""))).strip()[:limit]


def _postcode(value):
    """An Indian PIN code as six digits when it is one ("577 002" -> "577002"); anything else is shown as written, trimmed."""
    text = _text(value, 12)
    compact = re.sub(r"\s", "", text)
    return compact if re.fullmatch(r"\d{6}", compact) else text


def address_parts(tags):
    """
    What the listing says about where the store is, never more: {text, street, locality, town, district, state, postcode, level}.
    level: "full" (a street, a locality or town, and a PIN code), "partial" (something, but not all), "none" (nothing listed).
    """
    full = _text(tags.get("addr:full"), 250)
    if full:
        return {"text": full, "street": None, "locality": None, "town": None, "district": None, "state": None, "postcode": None, "level": "full"}
    street_name = _text(tags.get("addr:street")) or _text(tags.get("addr:place"))
    number_and_street = " ".join(p for p in (_text(tags.get("addr:housenumber"), 40), _text(tags.get("addr:street"))) if p)
    street = ", ".join(p for p in (_text(tags.get("addr:housename")), number_and_street or _text(tags.get("addr:place"))) if p)
    block = _text(tags.get("addr:block"), 60)
    if block and not re.search(r"block", block, re.IGNORECASE):
        block = f"Block {block}"                                # a bare "G" reads as nothing; the tag is a block
    locality = ", ".join(p for p in (block, _text(tags.get("addr:suburb") or tags.get("addr:neighbourhood") or tags.get("addr:hamlet")),
                                     _text(tags.get("addr:subdistrict"))) if p)
    town = _text(tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village"))
    district = _text(tags.get("addr:district"))
    state = _text(tags.get("addr:state"))
    postcode = _postcode(tags.get("addr:postcode"))
    listed = []
    for part in (street, locality, town, district, state, postcode):
        if part and part.lower() not in {x.lower() for x in listed}:        # "Davanagere" as town and district is said once
            listed.append(part)
    text = ", ".join(listed) or None
    if not text:
        level = "none"
    elif street_name and (locality or town) and postcode:      # a house number alone is not a street
        level = "full"
    else:
        level = "partial"
    return {"text": text, "street": street or None, "locality": locality or None, "town": town or None, "district": district or None,
            "state": state or None, "postcode": postcode or None, "level": level}


def build_address(tags):
    """The address as one line, or None when the listing has none."""
    return address_parts(tags)["text"]


def store_name(tags):
    """The name the listing carries (name, then English name, official name, brand, then any other-language name), or None. Never made up."""
    for key in ("name", "name:en", "official_name", "brand"):
        value = _text(tags.get(key))
        if value:
            return value
    for key in sorted(k for k in tags if k.startswith("name:")):
        value = _text(tags[key])
        if value:
            return value
    return None


def _phone(tags):
    raw = (tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile") or tags.get("mobile") or "").strip()
    if not raw or not _PHONE_OK.match(raw):
        return None, None
    first = re.split(r"[;,]", raw)[0].strip()
    digits = ("+" if first.startswith("+") else "") + re.sub(r"\D", "", first)
    return raw, (f"tel:{digits}" if len(re.sub(r"\D", "", digits)) >= 6 else None)


def _website(tags):
    url = (tags.get("website") or tags.get("contact:website") or "").strip()
    return url if re.match(r"^https?://[^\s]+$", url, re.IGNORECASE) else None


def _last_edited(element):
    stamp = element.get("timestamp")
    if not stamp:
        return None
    try:
        return datetime.strptime(stamp[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _position(element):
    if "lat" in element and "lon" in element:
        return element["lat"], element["lon"]
    center = element.get("center") or {}
    return center.get("lat"), center.get("lon")


def _normalized_name(name):
    return re.sub(r"[\W_]+", " ", (name or "").casefold()).strip()


def _phone_numbers(tags):
    """The listed phone numbers as their last ten digits, so "+91-80-2286-8423" and "080 2286 8423" compare equal."""
    numbers = set()
    for key in ("phone", "contact:phone", "contact:mobile", "mobile"):
        for part in re.split(r"[;,]", str(tags.get(key) or "")):
            digits = re.sub(r"\D", "", part)
            if len(digits) >= 6:
                numbers.add(digits[-10:])
    return numbers


# Two entries are the SAME store only on evidence, never because they are close: shops are often a few metres apart (a real search found
# "Medicine House" and "Nath Brothers" 4 m apart, with different phone numbers). Both must carry the same name, sit within these distances (a
# building outline's centre can be further from a shop's point than two points are from each other), and contradict each other on nothing.
DUPLICATE_MAX_METRES = {"points": 25, "outline": 60}


def _conflict(tags_a, tags_b):
    """What the two listings say that cannot both be about one shop, or None."""
    phones_a, phones_b = _phone_numbers(tags_a), _phone_numbers(tags_b)
    if phones_a and phones_b and not (phones_a & phones_b):
        return "different phone numbers"
    for key, label in (("branch", "different branches"), ("ref", "different reference numbers"), ("addr:housenumber", "different house numbers"),
                       ("addr:street", "different streets"), ("addr:postcode", "different PIN codes")):
        a, b = _normalized_name(tags_a.get(key)), _normalized_name(tags_b.get(key))
        if a and b and a != b:
            return label
    return None


def likely_duplicate(a, b):
    """
    Why two parsed entries are probably one store listed twice (a point and a building outline, say), or None. `a` and `b` are the internal
    records of parse_elements: {"store", "tags", "kind"}. A missing name never qualifies: with no name there is nothing to say they are the same.
    """
    name_a, name_b = a["store"]["name"], b["store"]["name"]
    if not (a["store"]["name_listed"] and b["store"]["name_listed"]) or _normalized_name(name_a) != _normalized_name(name_b):
        return None
    metres = haversine_m(a["store"]["lat"], a["store"]["lon"], b["store"]["lat"], b["store"]["lon"])
    limit = DUPLICATE_MAX_METRES["points" if a["kind"] == "node" and b["kind"] == "node" else "outline"]
    if metres > limit or _conflict(a["tags"], b["tags"]):
        return None
    shared = []
    if _phone_numbers(a["tags"]) & _phone_numbers(b["tags"]):
        shared.append("the same phone number")
    return {"metres": int(round(metres)), "reason": f"the same name, {int(round(metres))} m apart" + (f", {shared[0]}" if shared else "") + ", and nothing that differs"}


def _richness(record):
    """How much the entry says (a duplicate is merged into the one that says most)."""
    s = record["store"]
    return sum(1 for v in (s["name_listed"], s["address"], s["phone"], s["opening_hours"], s["website"]) if v)


def merge_duplicates(records):
    """
    Groups entries that are likely one store (see likely_duplicate) and keeps one per group: the entry that says most, then a point over an
    outline (a more exact position), then the more recently edited. The others are named on it as `also_listed_as`; their details are NOT
    copied over, because if the judgement were wrong that would put one shop's phone number on another. Entries without a name never merge.
    """
    by_name = defaultdict(list)
    for record in records:
        if record["store"]["name_listed"]:
            by_name[_normalized_name(record["store"]["name"])].append(record)
    parent = {id(r): r for r in records}
    link = {}

    def find(r):
        while parent[id(r)] is not r:
            r = parent[id(r)]
        return r

    for group in by_name.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                evidence = likely_duplicate(group[i], group[j])
                if evidence:
                    ra, rb = find(group[i]), find(group[j])
                    if ra is not rb:
                        parent[id(rb)] = ra
                    link[(id(group[i]), id(group[j]))] = evidence
    groups = defaultdict(list)
    for record in records:
        groups[id(find(record))].append(record)
    kept = []
    for members in groups.values():
        members.sort(key=lambda r: (-_richness(r), r["kind"] != "node", -(r["edited_ordinal"] or 0), r["store"]["store_id"]))
        winner = members[0]
        winner["store"]["also_listed_as"] = []
        for other in members[1:]:
            evidence = link.get((id(winner), id(other))) or link.get((id(other), id(winner)))
            if not evidence:                                  # linked through a third entry: describe the pair we can measure
                evidence = {"metres": int(round(haversine_m(winner["store"]["lat"], winner["store"]["lon"], other["store"]["lat"], other["store"]["lon"]))),
                            "reason": "the same name, close by, and nothing that differs"}
            winner["store"]["also_listed_as"].append({"store_id": other["store"]["store_id"], "metres_apart": evidence["metres"], "reason": evidence["reason"]})
        kept.append(winner)
    return kept


def parse_elements(elements, origin, scope="all", today=None):
    """
    The stores in an Overpass reply, nearest first. `scope` keeps all of them, only Jan Aushadhi Kendras, Kendras and generic stores, or only the
    other pharmacies (SCOPE_CATEGORIES). An entry listed twice (see likely_duplicate) appears once, with the other listing named on it.
    """
    if scope not in SCOPE_CATEGORIES:
        raise ValueError(f"scope must be one of {', '.join(SCOPES)}")
    wanted = SCOPE_CATEGORIES[scope]
    today = today or date.today()
    records, seen = [], set()
    for element in elements or []:
        tags = element.get("tags") or {}
        kind, osm_id = element.get("type"), element.get("id")
        lat, lon = _position(element)
        if kind not in ("node", "way", "relation") or not isinstance(osm_id, int) or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        category = classify(tags)
        if wanted is not None and category not in wanted:
            continue
        store_id = f"osm:{kind}/{osm_id}"
        if store_id in seen:
            continue
        seen.add(store_id)
        phone, phone_link = _phone(tags)
        metres = haversine_m(origin[0], origin[1], lat, lon)
        name = store_name(tags)
        address = address_parts(tags)
        edited = _last_edited(element)
        edited_date = date.fromisoformat(edited) if edited else None
        records.append({
            "kind": kind, "tags": tags, "edited_ordinal": edited_date.toordinal() if edited_date else None,
            "store": {
                "store_id": store_id,
                "name": name or NAME_UNAVAILABLE, "name_listed": bool(name),
                "category": category, "category_label": CATEGORY_LABELS[category],
                "address": address["text"], "address_level": address["level"],
                "address_parts": {k: address[k] for k in ("street", "locality", "town", "postcode")},
                "lat": round(lat, 6), "lon": round(lon, 6),
                "distance_m": int(round(metres)), "distance_text": distance_text(metres),
                "phone": phone, "phone_link": phone_link, "website": _website(tags),
                "opening_hours": _text(tags.get("opening_hours"), 200) or None,
                "directions_url": directions_url(lat, lon),
                "source": "OpenStreetMap", "listing_last_edited": edited,
                # an old listing may no longer be right: said next to its date (a policy setting, not a measurement)
                "listing_old": bool(edited_date and (today - edited_date).days > Config.STORE_LISTING_OLD_DAYS),
                "also_listed_as": [],
                "verified": False,
            },
        })
    stores = [r["store"] for r in merge_duplicates(records)]
    stores.sort(key=lambda st: (st["distance_m"], st["name"].lower(), st["store_id"]))
    return stores


# --- asking OpenStreetMap ------------------------------------------------------------------------------------------------------

def build_query(lat, lon, radius_m, limit):
    """Overpass QL: every pharmacy / chemist within the radius. The name filter is applied in code, where it is cheap and testable."""
    around = f"(around:{int(radius_m)},{lat:.{COORDINATE_DECIMALS}f},{lon:.{COORDINATE_DECIMALS}f})"
    return (
        f"[out:json][timeout:{int(Config.PLACES_TIMEOUT_SECONDS)}];\n"
        f"(\n  nwr{around}[\"amenity\"=\"pharmacy\"];\n  nwr{around}[\"healthcare\"=\"pharmacy\"];\n  nwr{around}[\"shop\"=\"chemist\"];\n);\n"
        f"out center meta {int(limit)};"
    )


def _headers():
    return {"User-Agent": Config.PLACES_USER_AGENT, "Accept": "application/json"}


def fetch_overpass(query):
    """The parsed JSON reply, or PlacesUnavailable with a message that is safe to show."""
    if Config.PLACES_PROVIDER != "osm_overpass":
        raise PlacesNotConfigured(
            "Nearby store search is not set up on this server. See docs/STORE_FINDER_SETUP.md (PLACES_PROVIDER and OVERPASS_URL)."
        )
    # Public Overpass servers are often busy, so the configured servers are tried in turn and the first usable answer is used. When
    # all of them fail, the LAST failure is reported (never an empty "no stores" answer).
    started, last = time.monotonic(), None
    for url in overpass_urls():
        if last is not None and time.monotonic() - started > Config.PLACES_TOTAL_BUDGET_SECONDS:
            break
        try:
            return _read_overpass(_post_overpass(url, query))
        except PlacesUnavailable as exc:
            last = exc
    raise last


def overpass_urls():
    """The primary server first, then the fallbacks, without repeats."""
    urls = [Config.OVERPASS_URL] + [u.strip() for u in Config.OVERPASS_FALLBACK_URLS.split(",")]
    return list(dict.fromkeys(u for u in urls if u))


def _post_overpass(url, query):
    try:
        return requests.post(url, data={"data": query}, headers=_headers(), timeout=(5, Config.PLACES_TIMEOUT_SECONDS + 2))
    except requests.RequestException:
        raise PlacesUnavailable("The store listing service could not be reached. Please try again in a minute.")


def _read_overpass(response):
    if response.status_code in (429, 502, 503, 504):
        raise PlacesUnavailable("The store listing service is busy right now. Please try again in a minute.")
    if response.status_code != 200:
        raise PlacesUnavailable("The store listing service returned an error. Please try again later.")
    try:
        body = response.json()
    except ValueError:
        raise PlacesUnavailable("The store listing service returned something unreadable. Please try again later.")
    if not isinstance(body, dict) or not isinstance(body.get("elements"), list):
        raise PlacesUnavailable("The store listing service returned something unexpected. Please try again later.")
    if body.get("remark") and not body["elements"] and "timed out" in str(body["remark"]).lower():
        raise PlacesUnavailable("The store listing service ran out of time for this area. Try a smaller distance.")
    return body


_cache, _cache_lock = {}, threading.Lock()


def _cached(key, producer):
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < Config.STORE_CACHE_SECONDS:
            return hit[1]
    value = producer()
    with _cache_lock:
        if len(_cache) >= 200:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
        _cache[key] = (now, value)
    return value


def clear_cache():
    with _cache_lock:
        _cache.clear()


def search_nearby(lat, lon, radius_km=None, scope="all", fetch=None):
    """
    The stores near a place, nearest first, as the screens present them.
    Raises ValueError for a bad request and PlacesUnavailable when OpenStreetMap cannot be reached.
    """
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {', '.join(SCOPES)}")
    lat, lon = clean_coordinates(lat, lon)
    radius_km = clean_radius_km(radius_km if radius_km is not None else Config.STORE_DEFAULT_RADIUS_KM)
    query = build_query(lat, lon, radius_km * 1000, Config.STORE_FETCH_LIMIT)
    body = _cached(("nearby", query), lambda: (fetch or fetch_overpass)(query))
    found = [s for s in parse_elements(body["elements"], (lat, lon), scope) if s["distance_m"] <= radius_km * 1000]
    stores = found[: Config.STORE_MAX_RESULTS]
    return {
        "center": {"lat": lat, "lon": lon}, "radius_km": radius_km, "scope": scope, "count": len(stores), "stores": stores,
        # how many stores there were within the distance: more than are shown when the list is cut to the nearest ones, which the page says
        "total_found": len(found),
        # what the list holds, by kind (the map's key reads from this) and how many entries were folded into another as a likely duplicate
        "category_counts": {c: sum(1 for st in stores if st["category"] == c) for c in CATEGORY_LABELS},
        "duplicates_merged": sum(len(st["also_listed_as"]) for st in stores),
        "may_be_incomplete": len(body["elements"]) >= Config.STORE_FETCH_LIMIT,
        "attribution": ATTRIBUTION, "verification_note": NOT_VERIFIED_NOTE, "official_locator_url": OFFICIAL_LOCATOR_URL,
        "location_note": "Your position was rounded to about 100 m for this search and is not stored.",
    }


# --- turning a typed place name into a position (when the person does not share their location) -------------------------------

_geocode_lock, _last_geocode = threading.Lock(), [0.0]


def geocode(query, fetch=None):
    """Up to five places for a typed name, via Nominatim, only when the person asks. [{label, lat, lon}] with positions rounded to ~100 m."""
    query = re.sub(r"\s+", " ", (query or "")).strip()
    if len(query) < 3 or len(query) > 100:
        raise ValueError("Type a place name or PIN code of 3 to 100 characters")
    if Config.PLACES_PROVIDER != "osm_overpass":
        raise PlacesNotConfigured("Place search is not set up on this server. See docs/STORE_FINDER_SETUP.md.")

    def ask():
        if fetch:
            return fetch(query)
        with _geocode_lock:                                       # Nominatim's policy: at most one request a second
            wait = 1.0 - (time.monotonic() - _last_geocode[0])
            if wait > 0:
                time.sleep(wait)
            _last_geocode[0] = time.monotonic()
        try:
            response = requests.get(
                f"{Config.NOMINATIM_URL.rstrip('/')}/search", headers=_headers(), timeout=Config.PLACES_TIMEOUT_SECONDS,
                params={"q": query, "format": "jsonv2", "countrycodes": "in", "limit": 5, "addressdetails": 0},
            )
        except requests.RequestException:
            raise PlacesUnavailable("The place search could not be reached. Please try again in a minute.")
        if response.status_code != 200:
            raise PlacesUnavailable("The place search is busy right now. Please try again in a minute.")
        try:
            return response.json()
        except ValueError:
            raise PlacesUnavailable("The place search returned something unreadable. Please try again later.")

    found = _cached(("geocode", query.lower()), ask)
    places = []
    for item in found if isinstance(found, list) else []:
        try:
            lat, lon = clean_coordinates(item["lat"], item["lon"])
        except (KeyError, ValueError):
            continue
        label = str(item.get("display_name") or "").strip()
        if label:
            places.append({"label": label[:160], "lat": lat, "lon": lon})
    return {"query": query, "places": places, "attribution": "Place search © OpenStreetMap contributors (Nominatim)."}
