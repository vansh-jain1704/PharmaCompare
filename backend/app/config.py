import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "pharmacompare_app")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "pharmacompare")

    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

    FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads", "prescriptions"))
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}

    # --- OCR ---------------------------------------------------------------
    # "auto"    : cloud OCR when credentials are present, EasyOCR otherwise
    # "cloud"   : cloud only - fail loudly instead of silently falling back
    # "easyocr" : local only, ignoring any configured credentials
    OCR_PROVIDER = os.getenv("OCR_PROVIDER", "auto").strip().lower()

    # Google Cloud Vision. Never hardcoded - supplied via .env / environment.
    GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY", "").strip()
    GOOGLE_VISION_ENDPOINT = os.getenv(
        "GOOGLE_VISION_ENDPOINT", "https://vision.googleapis.com/v1/images:annotate"
    )
    CLOUD_OCR_TIMEOUT_SECONDS = int(os.getenv("CLOUD_OCR_TIMEOUT_SECONDS", "30"))

    # --- Medicine explanations ---------------------------------------------
    # Google Gemini, for the "Explain this medicine" feature. Without a key
    # the app falls back to a deterministic explainer built from the stored
    # record, so the feature works offline and at no cost.
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_ENDPOINT = os.getenv(
        "GEMINI_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta"
    )
    LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "20"))

    # --- Photo quality warnings ---------------------------------------------------
    # Heuristic DEFAULTS for the warnings in app/services/image_quality_service.py (see its docstring for how they were chosen
    # and why five photos cannot validate them). They only ever warn: they never block an upload or change what the OCR reads.
    IMAGE_MIN_SIDE_PIXELS = int(os.getenv("IMAGE_MIN_SIDE_PIXELS", "600"))
    IMAGE_MIN_SHARPNESS = float(os.getenv("IMAGE_MIN_SHARPNESS", "20"))
    IMAGE_MIN_BRIGHTNESS = float(os.getenv("IMAGE_MIN_BRIGHTNESS", "70"))
    IMAGE_MIN_CONTRAST = float(os.getenv("IMAGE_MIN_CONTRAST", "15"))

    # --- Pharmacy price and stock reports ----------------------------------------
    # How old a pharmacy's report may be and still be presented as describing NOW. These are POLICY settings, not
    # measurements (stock changes faster than prices, so it goes stale sooner). The real age of every report is always shown.
    OFFER_STOCK_MAX_AGE_HOURS = int(os.getenv("OFFER_STOCK_MAX_AGE_HOURS", "48"))
    OFFER_PRICE_MAX_AGE_DAYS = int(os.getenv("OFFER_PRICE_MAX_AGE_DAYS", "7"))
    # After this many days a reference-dataset snapshot is called old on screen and in the PDF. A POLICY setting, not a measurement: the
    # dataset's own price dates are unknown, so the age is that of the import.
    REFERENCE_PRICE_STALE_DAYS = int(os.getenv("REFERENCE_PRICE_STALE_DAYS", "180"))

    # --- Partner feed API (POST /api/feeds/offers): limits so one partner cannot flood the table or the server ---------
    PARTNER_FEED_MAX_ROWS = int(os.getenv("PARTNER_FEED_MAX_ROWS", "500"))
    PARTNER_FEED_MAX_BYTES = int(os.getenv("PARTNER_FEED_MAX_BYTES", "300000"))
    PARTNER_FEED_REQUESTS_PER_MINUTE = int(os.getenv("PARTNER_FEED_REQUESTS_PER_MINUTE", "30"))

    # --- Nearby generic medicine stores (see docs/STORE_FINDER_SETUP.md) ---------------------------------------------
    # osm_overpass = store listings from OpenStreetMap through an Overpass server; off = the feature reports that it is not set up.
    # Public Overpass servers are for light, human-operated use: point OVERPASS_URL at your own instance for anything more. The servers are
    # tried in order, so a busy one does not stop the feature. (Which public servers answer changes from day to day; on 2026-10-18 only the
    # first one below did. Their usage policies have not been reviewed here.)
    PLACES_PROVIDER = os.getenv("PLACES_PROVIDER", "osm_overpass").strip().lower()
    OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass.openstreetmap.fr/api/interpreter").strip()
    OVERPASS_FALLBACK_URLS = os.getenv("OVERPASS_FALLBACK_URLS", "https://overpass-api.de/api/interpreter,https://overpass.kumi.systems/api/interpreter").strip()
    PLACES_TOTAL_BUDGET_SECONDS = int(os.getenv("PLACES_TOTAL_BUDGET_SECONDS", "40"))
    NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org").strip()
    # Identifies this application to the OpenStreetMap services (their usage policies require it). Add a contact address in .env.
    PLACES_USER_AGENT = os.getenv("PLACES_USER_AGENT", "PharmaCompare/1.0 (student project, generic medicine store finder)").strip()
    PLACES_TIMEOUT_SECONDS = int(os.getenv("PLACES_TIMEOUT_SECONDS", "20"))
    STORE_DEFAULT_RADIUS_KM = float(os.getenv("STORE_DEFAULT_RADIUS_KM", "5"))
    STORE_MAX_RADIUS_KM = float(os.getenv("STORE_MAX_RADIUS_KM", "25"))
    STORE_MAX_RESULTS = int(os.getenv("STORE_MAX_RESULTS", "30"))
    STORE_FETCH_LIMIT = int(os.getenv("STORE_FETCH_LIMIT", "400"))
    STORE_CACHE_SECONDS = int(os.getenv("STORE_CACHE_SECONDS", "300"))
    # a store listing not edited for this many days is shown with "may be out of date" (3 years). A POLICY setting, not a measurement.
    STORE_LISTING_OLD_DAYS = int(os.getenv("STORE_LISTING_OLD_DAYS", "1095"))
