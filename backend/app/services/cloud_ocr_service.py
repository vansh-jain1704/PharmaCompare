"""
Cloud OCR for handwritten prescriptions - Google Cloud Vision.

WHY THIS PROVIDER (measured against what this pipeline actually needs):

  * Handwriting is the whole point. Vision's DOCUMENT_TEXT_DETECTION is the
    dense-document model and reads handwriting; its TEXT_DETECTION sibling
    targets sparse text in photos and is the wrong tool here. Local EasyOCR
    returned 'Aop"u-$' for "T. Anrue-p" on a real prescription, and no
    amount of preprocessing moved it (six variants tested).
  * Credentials stay simple. Vision authenticates with a plain API key on
    the query string, so there is no service-account JSON, no OAuth dance
    and no vendor SDK - one HTTPS POST. Azure's Read model is comparably
    good at handwriting but needs an endpoint+key pair and an async submit/
    poll cycle; AWS Textract needs SigV4 signing or boto3. For a project
    that has to be handed over and run by someone else, the simplest
    credential story wins.
  * It returns per-word bounding boxes and confidences, which is exactly
    what the existing line-grouping logic consumes - so cloud and local OCR
    produce the same shape, and everything downstream is untouched.
  * Its free tier covers ordinary project use.

This module NEVER fabricates text. If the call fails, the key is missing or
the response is malformed, it raises - and ocr_service falls back to
EasyOCR so the Option A flow still works.
"""
import base64
import logging
import os
import re
import traceback
from urllib.parse import quote

import requests

from app.config import Config

VISION_FEATURE = "DOCUMENT_TEXT_DETECTION"
# Tells Vision which languages to expect; it still returns whatever it reads. Hindi is included because Indian prescriptions often carry a
# handwritten Hindi note ("सुबह खाने बाद" = morning, after food). With English only, Vision read that note as Latin gibberish ("2TTE 2016 OTG"),
# which then appeared as a sixth "medicine". Measured on a real prescription: with ["en", "hi"] the note is read in Devanagari and every English
# line comes back unchanged.
LANGUAGE_HINTS = ["en", "hi"]


# ---- keeping the API key out of every message --------------------------------------------------
# Vision authenticates with "?key=..." on the request URL, so the key can end up wherever that URL is
# quoted: in a requests exception ("... with url: /v1/images:annotate?key=AIza..."), in an upstream error
# body, in a traceback that chains the original exception, or in the HTTP library's debug log. Everything
# that is logged or returned to a client goes through redact_secrets() first.
_KEY_PARAM_RE = re.compile(r"(?i)([?&]key=)[^&\s'\")<>]+")
_GOOGLE_KEY_RE = re.compile(r"AIza[0-9A-Za-z_\-]{20,}")


def redact_secrets(value):
    """
    The text of `value` with the Vision API key removed: the configured key (raw and URL-encoded), any
    "key=" query parameter, and anything shaped like a Google API key. Ordinary diagnostics (host, port,
    status, exception type) are left alone.
    """
    text = str(value)
    key = Config.GOOGLE_VISION_API_KEY
    if key:
        text = text.replace(key, "***").replace(quote(key, safe=""), "***")
    text = _KEY_PARAM_RE.sub(r"\1***", text)
    return _GOOGLE_KEY_RE.sub("***", text)


def redacted_traceback(exc):
    """The full traceback of `exc`, chained causes included, as text with the key removed."""
    return redact_secrets("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))


class _RedactKeyFilter(logging.Filter):
    """Redacts the request line the HTTP library logs at DEBUG ("POST /v1/images:annotate?key=...")."""

    def filter(self, record):
        record.msg = redact_secrets(record.getMessage())
        record.args = ()
        return True


_http_logger = logging.getLogger("urllib3.connectionpool")
if not any(isinstance(f, _RedactKeyFilter) for f in _http_logger.filters):
    _http_logger.addFilter(_RedactKeyFilter())


class CloudOcrError(RuntimeError):
    """Raised for any reason the cloud result cannot be trusted or used. Its text never contains the key."""

    def __init__(self, message=""):
        super().__init__(redact_secrets(message))


def is_configured():
    return bool(Config.GOOGLE_VISION_API_KEY)


def _vertices_to_box(bounding_poly):
    """
    Google returns a bounding box as 4 vertices, and OMITS a coordinate when
    it is 0 - so a box touching the left edge has no 'x' key at all. Missing
    means zero, not missing.
    """
    vertices = (bounding_poly or {}).get("vertices") or []
    if len(vertices) < 3:
        return None
    return [[v.get("x", 0), v.get("y", 0)] for v in vertices]


def _words_from_response(payload):
    """
    Flattens Vision's page > block > paragraph > word tree into the
    (box, text, confidence) triples the local pipeline's line grouper
    already knows how to assemble into printed lines.
    """
    responses = payload.get("responses") or []
    if not responses:
        raise CloudOcrError("Vision returned no responses")

    first = responses[0]
    if "error" in first:
        message = (first["error"] or {}).get("message", "unknown Vision error")
        raise CloudOcrError(f"Vision reported an error: {redact_secrets(message)}")

    annotation = first.get("fullTextAnnotation")
    if not annotation:
        return []  # a genuinely blank/unreadable page, not a failure

    words = []
    for page in annotation.get("pages", []):
        for block in page.get("blocks", []):
            for paragraph in block.get("paragraphs", []):
                for word in paragraph.get("words", []):
                    text = "".join(s.get("text", "") for s in word.get("symbols", []))
                    if not text.strip():
                        continue
                    box = _vertices_to_box(word.get("boundingBox"))
                    if box is None:
                        continue
                    words.append((box, text, float(word.get("confidence", 0.0))))
    return words


def _encode_image(file_path, file_ext):
    """
    Vision's images:annotate takes image bytes. A PDF is rendered to its
    first page here rather than using the async files:annotate flow, which
    keeps this a single synchronous request and reuses the renderer the
    local path already relies on.
    """
    if file_ext == "pdf":
        # Imported lazily: the local OCR module pulls in torch/easyocr, and
        # the cloud path should not pay that cost just to read a PDF.
        from io import BytesIO

        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(file_path)
        try:
            image = pdf[0].render(scale=2.0).to_pil().convert("RGB")
        finally:
            pdf.close()
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    with open(file_path, "rb") as handle:
        return base64.b64encode(handle.read()).decode("ascii")


def extract_words(file_path, file_ext):
    """
    Runs Vision over one prescription file and returns
    [(bounding_box, text, confidence), ...] in Vision's own reading order.
    Raises CloudOcrError for anything that makes the result untrustworthy.
    """
    if not is_configured():
        raise CloudOcrError("GOOGLE_VISION_API_KEY is not set")

    if not os.path.exists(file_path):
        raise CloudOcrError(f"file not found: {file_path}")

    request_body = {
        "requests": [{
            "image": {"content": _encode_image(file_path, file_ext)},
            "features": [{"type": VISION_FEATURE}],
            "imageContext": {"languageHints": LANGUAGE_HINTS},
        }]
    }

    try:
        response = requests.post(
            Config.GOOGLE_VISION_ENDPOINT,
            params={"key": Config.GOOGLE_VISION_API_KEY},
            json=request_body,
            timeout=Config.CLOUD_OCR_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        # The exception text quotes the full URL, key included. Keep the kind of failure and the host/port,
        # drop the key, and do NOT chain the original exception ("from None"): a chained traceback prints it.
        raise CloudOcrError(f"could not reach Vision ({type(exc).__name__}): {redact_secrets(exc)}") from None

    if response.status_code != 200:
        # Surface the reason (bad key, billing disabled, quota) without ever
        # echoing the key itself.
        raise CloudOcrError(f"Vision HTTP {response.status_code}: {redact_secrets(response.text[:300])}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise CloudOcrError("Vision returned a non-JSON body") from exc

    return _words_from_response(payload)
