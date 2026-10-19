"""
Reading the dosing instructions of a prescription: when, how much, for how long.

Two things make this harder than it looks on a real (handwritten) prescription:

  * the instruction is written to the right of, or BELOW, the medicine name, so OCR returns it as separate lines
    ("T Lincont 100" / "x30dys"); an instruction row has to be attached to the medicine line above it;
  * OCR reads handwriting loosely: "1-0-0" comes back as "100", "x 7 days" as "X - 7 dys" or "sdays".

Everything here is read from text the prescription actually contains. Nothing is defaulted or assumed, and every
reading that is not certain says so:

  schedule_certainty  "written"          the schedule was read as written ("1-0-1")
                      "digits_run_together"  three digits that look like a schedule ("100"): POSSIBLY "1-0-0", but
                                          they may equally be a strength or a misread; always shown as "possible"
  duration_unreadable True when a number of days was clearly written but the number could not be read ("sdays")

A schedule has three slots (morning-afternoon-night) or four (morning-afternoon-evening-night).
"""
import re

SLOT_NAMES_3 = ("morning", "afternoon", "night")
SLOT_NAMES_4 = ("morning", "afternoon", "evening", "night")

# OCR confusions inside a hyphenated schedule: I / l / | read for 1, O / o read for 0.
_ONE = "1Il|"
_ZERO = "0Oo"
_SLOT = rf"[{_ONE}{_ZERO}2-9½¼¾](?:/\d)?"
SCHEDULE_RE = re.compile(
    rf"(?<![\w./])({_SLOT})\s*[-–—]\s*({_SLOT})\s*[-–—]\s*({_SLOT})(?:\s*[-–—]\s*({_SLOT}))?(?![\w./])"
)
# "100", "010", "101", "201": three digits, each 0-2, not all zero, standing alone (not part of a strength or a longer number)
DIGITS_RUN_RE = re.compile(r"(?<![\w./])([0-2]{3})(?![\w./%])(?!\s*(?:mg|mcg|ml|gm?|iu|%))", re.IGNORECASE)

_UNITS = r"(?:days?|dys?|dy|weeks?|wks?|wk|months?|mths?)"
_SHORT_UNITS = r"(?:d|w|m)"
# "x 30 days", "x30dys", "X - 7 dys", "for 5 days", "5 days", "x 30d"
DURATION_RE = re.compile(
    rf"(?:(?:\bx|×|\bfor\b)\s*[-–]?\s*(\d{{1,3}})\s*(?:{_UNITS}|{_SHORT_UNITS})\b|(?<![\w.])(\d{{1,3}})\s*{_UNITS}\b)",
    re.IGNORECASE,
)
# a duration word with a number that was not readable: "sdays", "#days", "Todays", "x 5days" is read above
UNREADABLE_DURATION_RE = re.compile(rf"(?:(?:\bx|×|\bfor\b)\s*[-–]?\s*)?(?<![\d\s])[^\W\d_]{{0,2}}{_UNITS}\b|#\s*{_UNITS}\b", re.IGNORECASE)

FREQUENCY_WORDS = [
    (re.compile(r"\bq\.?i\.?d\b|\bfour\s+times\b|\b4\s*times\b", re.I), "4 times daily"),
    (re.compile(r"\bt\.?d\.?s\b|\bt\.?i\.?d\b|\bthrice\b|\bthree\s+times\b|\b3\s*times\b", re.I), "3 times daily"),
    (re.compile(r"\bb\.?d\.?s?\b|\bb\.?i\.?d\b|\btwice\b|\b2\s*times\b", re.I), "Twice daily"),
    (re.compile(r"\bo\.?d\b|\bonce\s+(?:a\s+)?(?:day|daily)\b|\bonce\s+daily\b|\bevery\s+day\b", re.I), "Once daily"),
    (re.compile(r"\bonce\s+(?:in\s+)?(?:a\s+)?week(?:ly)?\b|\bweekly\b|\b1\s*/\s*week\b", re.I), "Once weekly"),
    (re.compile(r"\balternate\s+days?\b|\bevery\s+other\s+day\b", re.I), "Every other day"),
    (re.compile(r"\bh\.?s\b|\bat\s+night\b|\bbed\s*time\b|\bnightly\b", re.I), "At night"),
    (re.compile(r"\bs\.?o\.?s\b|\bp\.?r\.?n\b|\bas\s+(?:and\s+when\s+)?(?:needed|required)\b|\bif\s+(?:needed|required)\b", re.I), "As needed"),
]
TIMING_WORDS = [
    (re.compile(r"\bafter\s+(?:food|meals?|breakfast|lunch|dinner)\b|\ba\.?f\b|\bp\.?c\b", re.I), "after food"),
    (re.compile(r"\bbefore\s+(?:food|meals?|breakfast|lunch|dinner)\b|\bb\.?f\b|\(\s*b\s*/\s*f\s*\)|\ba\.?c\b", re.I), "before food"),
    (re.compile(r"\bempty\s+stomach\b", re.I), "on an empty stomach"),
]
DOSE_RE = re.compile(
    r"\b(\d+(?:\.\d+)?|½|1\s*/\s*2)\s*(tablets?|tabs?|capsules?|caps?|ml|mls|drops?|puffs?|sachets?|spoons?|tsp|teaspoons?)\b", re.I
)

# Devanagari words that commonly head a dosing note ("morning, after food"). Read only when the OCR returned them.
HINDI_TIMES = {"सुबह": "morning", "दोपहर": "afternoon", "शाम": "evening", "रात": "night"}
HINDI_TIMING_RE = [
    (re.compile("खाने\\s*(?:के\\s*)?बाद"), "after food"),
    (re.compile("खाने\\s*(?:से\\s*)?पहले"), "before food"),
]


def _slot_value(token):
    """The number of units in one slot: '1', '0', 'I'/'l' as 1, 'O' as 0, a half as 0.5."""
    t = token.strip()
    if "/" in t and t[0].isdigit():            # a written fraction ("1/2") before any single-character confusion below
        a, _, b = t.partition("/")
        try:
            return float(a) / float(b)
        except (ValueError, ZeroDivisionError):
            return None
    if t and t[0] in _ONE:
        return 1.0
    if t and t[0] in _ZERO:
        return 0.0
    if t.startswith("½") or t.replace(" ", "") == "1/2":
        return 0.5
    if t.startswith("¼"):
        return 0.25
    if t.startswith("¾"):
        return 0.75
    try:
        if "/" in t:
            a, b = t.split("/")
            return float(a) / float(b)
        return float(t)
    except ValueError:
        return None


def _format_amount(value):
    return str(int(value)) if value == int(value) else str(value)


def _frequency_from_slots(values):
    taken = sum(1 for v in values if v)
    if taken == 0:
        return None
    return {1: "Once daily", 2: "Twice daily", 3: "3 times daily", 4: "4 times daily"}.get(taken)


def _slots(values):
    names = SLOT_NAMES_3 if len(values) == 3 else SLOT_NAMES_4
    return {name: value for name, value in zip(names, values)}


def _timing_phrase(slots):
    """'morning and night' for the slots that are not zero."""
    taken = [name for name, value in slots.items() if value]
    if not taken:
        return None
    return taken[0] if len(taken) == 1 else ", ".join(taken[:-1]) + " and " + taken[-1]


def _duration_days(amount, unit):
    unit = unit.lower()
    if unit.startswith(("d", "dy")):
        return amount
    if unit.startswith("w"):
        return amount * 7
    return amount * 30    # a month is 30 days here; shown as written ("1 month"), the day count is only for the timeline


def parse(text):
    """
    What one line of text says about dosing. Every key is present; what the text does not say is None.

      schedule             "1-0-1" (written), or the three digits "100" when they only look like one
      schedule_certainty   "written" | "digits_run_together" | None
      slots                {"morning": 1.0, ...} or None
      frequency            "Twice daily", "Once weekly", "As needed", ...  or None
      dose                 "1 tablet" or None
      timing               "after food" / "before food" / "on an empty stomach" or None
      duration             "5 days" / "8 weeks" (as written) or None
      duration_days        5 / 56 or None
      duration_unreadable  True when a duration was written but its number could not be read
    """
    out = {"schedule": None, "schedule_certainty": None, "slots": None, "frequency": None, "dose": None, "timing": None,
           "duration": None, "duration_days": None, "duration_unreadable": False}
    if not text or not str(text).strip():
        return out
    text = str(text)

    match = SCHEDULE_RE.search(text)
    if match:
        values = [_slot_value(g) for g in match.groups() if g is not None]
        if all(v is not None for v in values) and any(values) and all(v <= 4 for v in values):
            out["schedule"] = "-".join(_format_amount(v) if v != 0.5 else "1/2" for v in values)
            out["schedule_certainty"] = "written"
            out["slots"] = _slots(values)
            out["frequency"] = _frequency_from_slots(values)
    else:
        run = DIGITS_RUN_RE.search(text)
        if run and any(c != "0" for c in run.group(1)):
            values = [float(c) for c in run.group(1)]
            out["schedule"] = "-".join(run.group(1))
            out["schedule_certainty"] = "digits_run_together"
            out["slots"] = _slots(values)
            out["frequency"] = _frequency_from_slots(values)

    for pattern, label in FREQUENCY_WORDS:
        if pattern.search(text):
            if out["frequency"] is None or label in ("Once weekly", "As needed", "Every other day"):
                out["frequency"] = label            # an explicit "once a week" outranks digits that merely look like a schedule
            break

    for pattern, label in TIMING_WORDS:
        if pattern.search(text):
            out["timing"] = label
            break
    if out["timing"] is None:
        for pattern, label in HINDI_TIMING_RE:
            if pattern.search(text):
                out["timing"] = label
                break

    dose = DOSE_RE.search(text)
    if dose:
        amount = dose.group(1).replace(" ", "")
        amount = "1/2" if amount in ("½", "1/2") else amount
        unit = dose.group(2).lower()
        unit = {"tab": "tablet", "tabs": "tablets", "cap": "capsule", "caps": "capsules"}.get(unit, unit)
        out["dose"] = f"{amount} {unit}"

    duration = DURATION_RE.search(text)
    if duration:
        number = int(duration.group(1) or duration.group(2))
        raw_unit = re.search(rf"{_UNITS}|{_SHORT_UNITS}", text[duration.start():duration.end()][len(str(number)):], re.IGNORECASE)
        unit_text = (raw_unit.group(0) if raw_unit else "d").lower()
        kind = "week" if unit_text.startswith("w") else "month" if unit_text.startswith("m") else "day"
        out["duration"] = f"{number} {kind}" + ("" if number == 1 else "s")
        out["duration_days"] = _duration_days(number, kind)
    elif UNREADABLE_DURATION_RE.search(text) and not re.search(r"\b(?:once|twice|daily|weekly)\b", text, re.I):
        out["duration_unreadable"] = True
    return out


def has_instruction(parsed):
    return any(parsed[k] for k in ("schedule", "frequency", "dose", "timing", "duration")) or parsed["duration_unreadable"]


def describe_schedule(parsed, short=False):
    """
    The schedule as one honest sentence ('1-0-1: morning and night', 'possibly 1-0-0'), or None. `short` is the form
    stored in the database (a 100-character column) and never drops the word "possibly".
    """
    if not parsed["schedule"]:
        return parsed["frequency"]
    phrase = _timing_phrase(parsed["slots"] or {})
    base = f"{parsed['schedule']}" + (f": {phrase}" if phrase else "")
    if parsed["schedule_certainty"] == "digits_run_together":
        digits = parsed["schedule"].replace("-", "")
        if short:
            return f"Possibly {parsed['schedule']} (digits read as {digits})"
        return f"possibly {base} (the digits were read as “{digits}”; check the prescription)"
    return base


def drop_schedule_that_is_a_strength(parsed, owned_numbers):
    """
    Three digits that look like a schedule ("100") are very often a real strength ("Lincer 100"). When the product the line
    was matched to HAS that number, the digits are its strength, not a schedule, and the possible schedule is removed.
    `owned_numbers` is a collection of canonical number strings ("100", "12.5") the product carries.
    """
    if parsed["schedule_certainty"] == "digits_run_together" and parsed["schedule"] and parsed["schedule"].replace("-", "") in set(owned_numbers):
        parsed = dict(parsed)
        parsed.update(schedule=None, schedule_certainty=None, slots=None)
        if parsed["frequency"] in ("Once daily", "Twice daily", "3 times daily", "4 times daily"):
            parsed["frequency"] = None
    return parsed


def merge(parts):
    """The instruction made of several lines (the medicine row and the rows below it): first reading of each field wins."""
    out = parse(None)
    for part in parts:
        for key, value in part.items():
            if key == "duration_unreadable":
                out[key] = out[key] or value
            elif out[key] in (None, False) and value not in (None, False):
                out[key] = value
    # a schedule read as digits only never beats one that was written
    if out["duration"]:
        out["duration_unreadable"] = False
    return out


def attach(medicine_texts, ocr_lines, is_medicine_line):
    """
    Which instruction belongs to which medicine line.

      medicine_texts   the OCR text of every line that is a medicine (in page order)
      ocr_lines        every OCR line, in order: [{"text": ...}, ...]
      is_medicine_line a function(text) -> True for a medicine line; any other line is a candidate instruction row

    A line that is not a medicine but says something about dosing is attached to the medicine line ABOVE it, as long as
    no other medicine line comes in between and it is within two lines of it (a handwritten "x 30 days" sits right below
    the name it belongs to). Returns {medicine text: {"instructions": merged dict, "sources": [texts used]}}.
    """
    result, current, gap = {}, None, 0
    texts = [(line.get("text") or "").strip() for line in ocr_lines]
    medicine_set = set(medicine_texts)
    for text in texts:
        if not text:
            continue
        if text in medicine_set and is_medicine_line(text):
            current, gap = text, 0
            result.setdefault(text, {"parts": [parse(text)], "sources": [text]})
            continue
        gap += 1
        if current is None or gap > 2:
            continue
        parsed = parse(text)
        if has_instruction(parsed):
            result[current]["parts"].append(parsed)
            result[current]["sources"].append(text)
    return {text: {"instructions": merge(v["parts"]), "sources": v["sources"]} for text, v in result.items()}


def owned_numbers(medicine):
    """Every number the product carries (ingredient strengths, strength column, numbers in its name), as canonical strings."""
    from app.services.composition import canonical_number, split_ingredients

    numbers = set()
    for _, ingredient_numbers in split_ingredients(medicine.get("composition")):
        numbers.update(ingredient_numbers)
    for text in (medicine.get("medicine_name"), medicine.get("strength")):
        numbers.update(canonical_number(n) for n in re.findall(r"\d+(?:\.\d+)?", text or ""))
    return numbers


def to_columns(parsed):
    """(dosage, frequency, duration) as the strings stored in Prescription_Medicines; any may be None."""
    dosage = None
    if parsed["dose"]:
        dosage = parsed["dose"] + (f", {parsed['timing']}" if parsed["timing"] else "")
    elif parsed["timing"]:
        dosage = parsed["timing"]
    return dosage, describe_schedule(parsed, short=True), parsed["duration"]

