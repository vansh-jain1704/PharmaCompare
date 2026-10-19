"""
A medicine the person types in themselves, for a prescription line the dataset cannot identify (a brand that is not in it).

What is stored is exactly what they typed, after trimming and a length check: a name, optionally a strength and a dosage form, and the
schedule and duration they read from the prescription. It is NOT matched to any product, so it never gets a price, a saving, an alternative
or a medicine-specific safety check, and it is shown as "Entered by you". The line keeps its original OCR text.

The typed details live beside the stored look-alikes in the line's existing match_options JSON ({"kind": "closest_guesses", "candidates": [...],
"user_entered": {...}}), so no schema change is needed. The typed schedule and duration go in the line's existing frequency and duration
columns.
"""
import json
import re

FORMS = ["Tablet", "Capsule", "Syrup", "Injection", "Drops", "Cream / ointment", "Powder / sachet", "Inhaler", "Other"]
KEY = "user_entered"

MAX_NAME, MAX_STRENGTH, MAX_FORM, MAX_TEXT = 100, 40, 30, 100
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _clean(value, limit, label, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    value = _CONTROL.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if required and len(value) < 2:
        raise ValueError(f"{label} is required (at least 2 characters)")
    if len(value) > limit:
        raise ValueError(f"{label} must be at most {limit} characters")
    return value or None


def validate(body):
    """The cleaned details {name, strength, form, schedule, duration}, or ValueError with a message safe to show."""
    if not isinstance(body, dict):
        raise ValueError("send the details as a JSON object")
    form = _clean(body.get("form"), MAX_FORM, "Form")
    if form and form not in FORMS:
        raise ValueError("Form must be one of: " + ", ".join(FORMS))
    return {
        "name": _clean(body.get("name"), MAX_NAME, "Medicine name", required=True),
        "strength": _clean(body.get("strength"), MAX_STRENGTH, "Strength"),
        "form": form,
        "schedule": _clean(body.get("schedule"), MAX_TEXT, "Schedule"),
        "duration": _clean(body.get("duration"), MAX_TEXT, "Duration"),
    }


def merge_into_options(match_options, details):
    """The match_options JSON text with the typed details added and any stored look-alikes kept."""
    try:
        decoded = match_options if isinstance(match_options, (list, dict)) else json.loads(match_options) if match_options else None
    except (TypeError, ValueError):
        decoded = None
    if isinstance(decoded, dict) and decoded.get("kind") == "closest_guesses":
        merged = dict(decoded)
    else:
        merged = {"kind": "closest_guesses", "candidates": []}
    merged[KEY] = {k: details[k] for k in ("name", "strength", "form")}
    return json.dumps(merged)


def decode(match_options):
    """The typed {name, strength, form} stored on a line, or None."""
    try:
        decoded = match_options if isinstance(match_options, (list, dict)) else json.loads(match_options) if match_options else None
    except (TypeError, ValueError):
        return None
    entry = decoded.get(KEY) if isinstance(decoded, dict) else None
    if isinstance(entry, dict) and entry.get("name"):
        return {"name": entry.get("name"), "strength": entry.get("strength"), "form": entry.get("form")}
    return None
