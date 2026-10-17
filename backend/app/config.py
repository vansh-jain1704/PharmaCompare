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
