"""
Pulls the dosage instructions out of a prescription line.

These are the Prescription_Medicines.dosage / frequency / duration columns,
which existed in the PPT's ER diagram but were never populated - every
medicine read "Not specified". They can only be filled once OCR fragments
are rejoined into whole printed lines (see ocr_service._group_into_rows),
because the instruction usually sits to the RIGHT of the medicine name.

Everything here is read from the text the prescription actually contains.
Nothing is inferred, defaulted, or assumed: a line that doesn't state a
frequency returns None for frequency, and the UI says "Not specified"
rather than inventing a plausible-looking schedule for a real medicine.
"""
import re

# Latin dosing abbreviations still in everyday use on Indian prescriptions,
# alongside the plain-English forms.
FREQUENCY_PATTERNS = [
    (re.compile(r"\bq\.?i\.?d\b|\bfour\s+times?\b|\b4\s*times?\b", re.I), "4 times daily"),
    (re.compile(r"\bt\.?i\.?d\b|\bt\.?d\.?s\b|\bthrice\b|\bthree\s+times?\b|\b3\s*times?\b", re.I), "3 times daily"),
    (re.compile(r"\bb\.?i\.?d\b|\bb\.?d\.?s?\b|\btwice\b|\b2\s*times?\b", re.I), "Twice daily"),
    (re.compile(r"\bo\.?d\b|\bonce\s+(?:a\s+)?(?:day|daily)\b|\bonce\s+daily\b|\bevery\s+day\b", re.I), "Once daily"),
    (re.compile(r"\bq\s*(\d+)\s*h\b|\bevery\s+(\d+)\s*(?:hours?|hrs?)\b", re.I), None),  # filled from the number
    (re.compile(r"\bs\.?o\.?s\b|\bas\s+(?:and\s+when\s+)?(?:needed|required)\b|\bif\s+(?:needed|required)\b|\bp\.?r\.?n\b", re.I), "As needed"),
    (re.compile(r"\bh\.?s\b|\bat\s+night\b|\bbed\s*time\b|\bnightly\b", re.I), "At night"),
    (re.compile(r"\balternate\s+days?\b|\bevery\s+other\s+day\b", re.I), "Every other day"),
    (re.compile(r"\bweekly\b|\bonce\s+a\s+week\b", re.I), "Once weekly"),
    (re.compile(r"\bmorning\b|\bo\.?m\b", re.I), "In the morning"),
]

DURATION_RE = re.compile(
    r"(?:x|for|次)?\s*\b(\d+)\s*(day|days|week|weeks|month|months)\b", re.I
)

# "1 tablet", "2 caps", "5 ml", "1/2 tab" - how much is taken at a time.
DOSAGE_RE = re.compile(
    r"\b(\d+(?:\.\d+)?|\d+\s*/\s*\d+)\s*"
    r"(tablets?|tabs?|capsules?|caps?|ml|mls|drops?|puffs?|sachets?|spoons?|tsp|teaspoons?)\b",
    re.I,
)

TIMING_RE = re.compile(r"\b(before|after)\s+(food|meals?|breakfast|lunch|dinner)\b", re.I)


def parse_frequency(text):
    if not text:
        return None
    for pattern, label in FREQUENCY_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        if label is not None:
            return label
        hours = next((g for g in match.groups() if g), None)
        return f"Every {hours} hours" if hours else None
    return None


def parse_duration(text):
    if not text:
        return None
    match = DURATION_RE.search(text)
    if not match:
        return None
    amount, unit = match.group(1), match.group(2).lower().rstrip("s")
    return f"{amount} {unit}" if amount == "1" else f"{amount} {unit}s"


def parse_dosage(text):
    """
    How much is taken per administration, plus any before/after-food note.
    Skips the strength written into the medicine name itself ("650mg") -
    that is the product, not the instruction.
    """
    if not text:
        return None
    parts = []
    match = DOSAGE_RE.search(text)
    if match:
        amount = re.sub(r"\s+", "", match.group(1))
        parts.append(f"{amount} {match.group(2).lower()}")
    timing = TIMING_RE.search(text)
    if timing:
        parts.append(f"{timing.group(1).lower()} {timing.group(2).lower()}")
    return ", ".join(parts) if parts else None


def parse_instructions(text):
    """
    Returns (dosage, frequency, duration) - any of which may be None. The patterns above read the plain-English forms;
    what they cannot read ("1-0-1", "x30dys", "X - 7 dys") is read by instruction_service, which also says so when a
    reading is only possible (digits that merely look like a schedule are returned as "Possibly 1-0-0 ...").
    """
    from app.services import instruction_service

    parsed = instruction_service.parse(text)
    dosage, frequency, duration = parse_dosage(text), parse_frequency(text), parse_duration(text)
    if frequency is None or (parsed["schedule"] and parsed["schedule_certainty"] == "written"):
        frequency = instruction_service.describe_schedule(parsed, short=True) or frequency
    if duration is None:
        duration = parsed["duration"]
    if dosage is None and parsed["dose"]:
        dosage = parsed["dose"] + (f", {parsed['timing']}" if parsed["timing"] else "")
    return dosage, frequency, duration
