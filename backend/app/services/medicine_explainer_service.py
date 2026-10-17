"""
"Explain this medicine" - plain-language description of a medicine we hold.

Two engines behind one function:

  * Google Gemini, when GEMINI_API_KEY is configured. The model is given
    ONLY the fields stored for that medicine and is told to describe it, not
    to advise on it.
  * A deterministic explainer built from the same fields otherwise, so the
    feature works with no key, no network and no cost.

SAFETY POSTURE - this is a medicines app, so the model is fenced in hard:
  - The prompt carries the real record. The model is instructed to work
    only from it and to say when something isn't on file, because an
    invented strength or manufacturer here is a patient-safety problem,
    not a cosmetic one.
  - It must not give dosing, suitability, or start/stop advice. That is a
    prescriber's job and the app says so everywhere else; it would be
    incoherent to let a generated paragraph quietly cross that line.
  - The disclaimer is appended by US after generation, so it cannot be
    edited away, reworded or omitted by the model.
  - Generation failures fall back to the deterministic text rather than
    surfacing an error: the user still gets the real facts.
"""
import logging
import traceback
from urllib.parse import quote

import requests

from app.config import Config
from app.services.cloud_ocr_service import redact_secrets
from app.services.ingredient_notes import lookup as lookup_notes

logger = logging.getLogger(__name__)


# Gemini authenticates with "?key=..." on the request URL, so the key can end up wherever that URL is quoted:
# in a requests exception, in an upstream error body, or in a traceback that chains the original exception.
# Anything logged goes through _redact() first. (redact_secrets already removes "key=" parameters and
# Google-style keys and installs the filter on the HTTP library's debug log; this adds the configured Gemini key.)
def _redact(value):
    text = redact_secrets(value)
    key = Config.GEMINI_API_KEY
    if key:
        text = text.replace(key, "***").replace(quote(key, safe=""), "***")
    return text


def _redacted_traceback(exc):
    """The full traceback of `exc`, chained causes included, as text with the Gemini key removed."""
    return _redact("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))

DISCLAIMER = (
    "This is general information, not medical advice and not a diagnosis. It does not say "
    "whether this medicine is right for you, and any dose shown is only a usual adult figure - "
    "your doctor's prescription decides what applies to you. Always follow your doctor's "
    "prescription and ask your doctor or pharmacist about anything you are unsure of."
)

UNAVAILABLE_NOTE = "Detailed explanation unavailable in demo mode."

# The ingredient notes describe the ORAL medicine. They do not carry over to a
# cream, eye drop or injection of the same ingredient, so those get no notes.
# Adult dose figures apply only to solid oral forms; a liquid or drop is dosed
# by age and weight, so quoting an adult figure there would be unsafe.
SOLID_ORAL_FORMS = {"tablet", "capsule"}
LIQUID_ORAL_FORMS = {"syrup", "suspension", "drop", "drops", "liquid", "powder", "granules", "sachet"}
WEIGHT_BASED_DOSE = (
    "The dose depends on age and weight - follow your doctor's prescription or the pack instructions."
)

SECTION_FIELDS = (
    ("What it's for", "uses"),
    ("Common dose", "dose"),
    ("Key precautions", "precautions"),
    ("Common side effects", "side_effects"),
)

SYSTEM_RULES = """You explain medicines to patients in plain, calm language.

Rules you must follow exactly:
- Use ONLY the medicine record provided. Never add facts that are not in it.
- If a detail is not on file, say so plainly rather than guessing or filling it in.
- Describe what the medicine IS and what its active ingredients are generally used for.
- Do NOT give dosing instructions, do NOT say whether the reader should take it,
  do NOT suggest starting, stopping or changing any medicine, and do NOT diagnose.
- No greetings, no sign-off, no markdown, no bullet points, no headings.
- At most 3 short paragraphs, under 130 words total.
- Write for someone with no medical training."""


def is_configured():
    return bool(Config.GEMINI_API_KEY)


def _facts(medicine):
    """The record, written out for the prompt - and nothing beyond it."""
    def value(key, label):
        raw = medicine.get(key)
        return f"{label}: {raw}" if raw not in (None, "", "NA") else f"{label}: not on file"

    lines = [
        value("medicine_name", "Brand name"),
        value("composition", "Composition"),
        value("primary_salt", "Primary active ingredient"),
        value("secondary_salt", "Second active ingredient"),
        value("strength", "Strength"),
        value("form", "Dosage form"),
        value("manufacturer", "Manufacturer"),
        value("pack_size", "Pack size"),
    ]
    if medicine.get("is_discontinued"):
        lines.append("Status: marked discontinued by the manufacturer in our dataset")
    return "\n".join(lines)


def _deterministic(medicine):
    """
    Built straight from the record. Reads naturally but states only what is
    stored, so it stays usable as the no-key default rather than a stub.
    """
    name = medicine.get("medicine_name") or "This medicine"
    salt = medicine.get("primary_salt")
    second = medicine.get("secondary_salt")
    strength = medicine.get("strength")
    form = (medicine.get("form") or "").lower()
    maker = medicine.get("manufacturer")
    composition = medicine.get("composition")

    first = f"{name} is "
    if form and form != "na":
        first += f"a {form.rstrip('s')} "
    else:
        first += "a medicine "
    if salt:
        ingredients = salt + (f" and {second}" if second else "")
        first += f"whose active ingredient{'s are' if second else ' is'} {ingredients}"
        first += f", at a strength of {strength}." if strength and strength != "NA" else "."
    else:
        first += "whose active ingredients are not recorded in our dataset."

    second_para = []
    if composition and composition != salt:
        second_para.append(f"Its full composition is listed as {composition}.")
    if maker:
        second_para.append(f"It is made by {maker}.")
    if medicine.get("pack_size"):
        second_para.append(f"It is sold as a {medicine['pack_size']}.")
    if medicine.get("is_discontinued"):
        second_para.append(
            "Our dataset marks this product as discontinued by its manufacturer, so a pharmacy "
            "may no longer stock it."
        )

    paragraphs = [first]
    if second_para:
        paragraphs.append(" ".join(second_para))
    return "\n\n".join(paragraphs)


def _structured_sections(medicine):
    """
    The four patient-facing blocks, from hand-written ingredient notes
    (ingredient_notes.py) - the database itself stores none of this.

    Returns (sections, complete). `complete` is False when any active
    ingredient has no notes; those are named rather than guessed at, and the
    caller adds the "unavailable" note. A single-ingredient medicine reads
    without labels; a combination labels each ingredient's line.
    """
    form = (medicine.get("form") or "").strip().lower()
    if form not in SOLID_ORAL_FORMS | LIQUID_ORAL_FORMS:
        return [], False
    ingredients = [i for i in (medicine.get("primary_salt"), medicine.get("secondary_salt")) if i and i != "NA"]
    known = [(name, lookup_notes(name)) for name in ingredients]
    covered = [(name, notes) for name, notes in known if notes]
    missing = [name for name, notes in known if not notes]

    sections = []
    for title, key in SECTION_FIELDS:
        if key == "dose" and covered and form in LIQUID_ORAL_FORMS:
            sections.append({"title": title, "text": WEIGHT_BASED_DOSE})
            continue
        if len(covered) == 1 and not missing:
            text = covered[0][1][key]
        else:
            text = "\n".join(f"{name}: {notes[key]}" for name, notes in covered)
        if text:
            sections.append({"title": title, "text": text})
    complete = bool(covered) and not missing
    return sections, complete


def _ask_gemini(medicine):
    endpoint = (
        f"{Config.GEMINI_ENDPOINT}/models/{Config.GEMINI_MODEL}:generateContent"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_RULES}]},
        "contents": [{
            "role": "user",
            "parts": [{"text": f"Medicine record:\n{_facts(medicine)}\n\nExplain this medicine."}],
        }],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 400},
    }

    try:
        response = requests.post(
            endpoint,
            params={"key": Config.GEMINI_API_KEY},
            json=payload,
            timeout=Config.LLM_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        # The exception text quotes the full URL, key included. Keep the kind of failure and the host/port,
        # drop the key, and do NOT chain the original exception ("from None"): a chained traceback prints it.
        raise RuntimeError(f"could not reach Gemini ({type(exc).__name__}): {_redact(exc)}") from None
    if response.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {_redact(response.text[:200])}")

    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise RuntimeError("Gemini returned an empty explanation")
    return text


def explain(medicine):
    """
    Returns {"text", "source", "disclaimer"}. Never raises: an explanation
    failing is not a reason to deny the user the facts we already hold.
    """
    if is_configured():
        try:
            return {
                "text": _ask_gemini(medicine),
                "source": "gemini",
                "disclaimer": DISCLAIMER,
            }
        except Exception as exc:
            # same diagnostics as logger.exception (message and full traceback), with the API key removed
            logger.error("Gemini explanation failed; using the record-based explainer: %s", _redacted_traceback(exc))

    sections, complete = _structured_sections(medicine)
    return {
        "text": _deterministic(medicine),
        "sections": sections,
        # Present whenever any part could not be explained, so a gap is
        # never mistaken for "nothing to know".
        "note": None if complete else UNAVAILABLE_NOTE,
        "source": "database",
        "disclaimer": DISCLAIMER,
    }
