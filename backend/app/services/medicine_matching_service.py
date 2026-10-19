"""
Medicine Detection: takes one line of OCR text and tries to identify a real
medicine from our local Medicines table.

Design (see project conversation for the full reasoning):
  1. FULLTEXT candidate retrieval (MySQL BOOLEAN MODE, wildcard prefixes) -
     cheap and tolerant of minor spelling differences ("Amoxicillin" vs the
     dataset's "Amoxycillin"), but MySQL relevance alone is not trustworthy
     enough to call something "identified".
  2. Python-side fuzzy string scoring (stdlib difflib) between the OCR line
     and each candidate's name/salt, corroborated by strength and dosage
     form agreement where the OCR text mentions them.

Confidence model (rewritten to fix a false-positive class - see
project conversation "Cardiology" -> "BIOPLEGIA INJECTION" bug):
  - Fuzzy text similarity ALONE is never enough on its own to confirm a
    medicine unless it is very high (MATCH_THRESHOLD_TEXT_ONLY) - ordinary
    words that happen to share a Latin/Greek medical root with a real drug
    or salt name (e.g. "Cardiology" vs the salt "Cardioplegia") can score
    a deceptively high whole-string ratio without actually being the same
    word.
  - When the OCR line also mentions a strength and/or dosage form that
    AGREES with the candidate, that corroboration allows a meaningfully
    lower text-similarity bar (MATCH_THRESHOLD_CORROBORATED) - this is
    what "medicine name + strength should receive stronger confidence"
    means in code, not just prose.
  - A CONFIRMED conflict (the line clearly states a different strength or
    form than the candidate) disqualifies a "matched" verdict outright,
    regardless of how high the text similarity is - never overridden by
    fuzzy text alone.
  - Ordinary prescription-header/administrative words and medical
    specialty names (Patient, Doctor, Diagnosis, Hospital, Date,
    Cardiology, Neurology, ...) are filtered out of consideration as a
    general class, not as one-off hardcoded exceptions for specific words
    that happened to cause a bug.

A line is only ever "matched" to a medicine_id when it clears the
appropriate threshold for the evidence actually available. Below that, it
is reported as needing verification - never silently guessed, never
auto-corrected.
"""
import re
from difflib import SequenceMatcher

from app.models.medicine_model import search_candidates, search_by_name_prefix, get_family_variants
from app.services import instruction_service
from app.services.display_rounding import percent
from app.services.composition import (
    canonical_number, composition_key, has_unknown_strength, ingredient_numerators, split_ingredients,
)
from app.services.release_type import detect_line_release, is_modified

# Two distinct bars, not one blended magic number:
#  - corroborated: text similarity + a real strength/form agreement
#  - text-only: nothing but fuzzy string similarity to go on
MATCH_THRESHOLD_CORROBORATED = 0.6
MATCH_THRESHOLD_TEXT_ONLY = 0.78

# Name similarity a product needs before it can be "matched" on a strength/form number
# alone. The score is 60% name + 40% corroboration, so a corroborating strength of 1.0 alone
# lifts a name similarity of only ~0.35 over the 0.6 bar: "Shelcal 500" became "Shellgel
# Softgel Capsule" because 500 happened to be its calcium carbonate strength. A candidate
# with real identity evidence (every word of the line found in its name, or every named
# ingredient present) is exempt; a bare number is not identity.
MIN_NAME_SIMILARITY_WITHOUT_IDENTITY = 0.6

# A name that merely LOOKS similar is not enough to settle a line automatically. Measured on 776
# OCR-corrupted real product names (see tests/test_autoconfidence.py): similar-looking matches
# below 0.90 were the wrong medicine 34 times in 128 (26%), at 0.90 and above 1 time in 147.
# Below the bar the line goes to the person, with the closest guess shown.
AUTO_MATCH_MIN_CONFIDENCE = 0.90

# Floor for showing a "closest guess" at all. Measured against real
# prescription scans: clinic addresses and letterheads score 0.22-0.42
# against some unrelated brand, while genuine medicines score 0.67+. Below
# this, naming a guess is worse than saying nothing - it filled the results
# table with things like "Near Valmiki Bhavana, ... Road" -> "Valmip-P
# Tablet". The line is still reported when it looks like a medicine; it
# just arrives without a bogus suggestion attached.
MIN_GUESS_SCORE = 0.5

MIN_WORD_LENGTH = 4
# Shortest run of letters that can still stand for a mangled medicine name.
# 'Aop"u-$' (really "Anrue-p") only offers three, so anything stricter
# silently loses real prescription lines.
MIN_SURFACEABLE_RUN = 3
# Brand stems can be short ("Pan-D", "Azee"). The FULLTEXT query keeps the
# stricter MIN_WORD_LENGTH, where short terms match far too much; a direct
# indexed name lookup can afford them.
MIN_PREFIX_WORD_LENGTH = 3
MAX_QUERY_WORDS = 6
WILDCARD_PREFIX_LEN = 5

WORD_RE = re.compile(r"[A-Za-z]+")
# Keeps numbers as their own tokens. A bare number is often the single most
# discriminative part of an Indian prescription line ("Dolo 650", "Telma 40"),
# so it must survive into scoring - dropping it made the correct product lose
# to shorter, unrelated names ("Dologel").
TOKEN_RE = re.compile(r"[A-Za-z]+|\d+")
STRENGTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|ml|gm?|iu|%)", re.IGNORECASE)
BARE_NUMBER_RE = re.compile(r"\b(\d+(?:\.\d+)?)\b")

# Name normalisation: anything that isn't a letter or digit separates words,
# except apostrophes, which close up ("Brand's" -> "brands").
APOSTROPHES = "'’ʼ`"
SEPARATOR_RE = re.compile(r"[^a-z0-9]+")

# "1." / "2)" at the start of a line - the doctor's numbering, not the drug.
# The trailing "." or ")" is required so a real leading dose ("5 ml") stays.
LIST_MARKER_RE = re.compile(r"^\s*\d{1,2}\s*[.)]\s*")
# Course length: "x 5 days", "x 5 d", "for 7 days". A time unit is required,
# so a strength like the 650 in "Dolo 650" is never mistaken for a duration.
# OCR often returns the multiplication sign for a handwritten or typed "x" ("x 10 days" -> "<multiplication sign> 10 days").
COURSE_LENGTH_RE = re.compile(
    r"(?:\b(?:x|for)|\u00d7)\s*\d+\s*(?:d|dys?|days?|w|wks?|weeks?|m|months?)\b", re.IGNORECASE
)

# Dosing schedule: "1-0-1" (morning-afternoon-night), "1-1-1-1", "0-0-1/2", "1 - 0 - 1".
# Single digits only, three or four slots, so a phone number or a strength pair ("500-125")
# is not mistaken for one. It must go before numbers are counted or compared: "Tab Dolo 650
# 1-0-1 x 5 days" has five numbers and was thrown away as a reference number, silently
# losing a real medicine line.
SCHEDULE_RE = re.compile(
    r"(?<![\d./])[\d\u00bd\u00bc\u00be](?:/\d)?(?:\s*[-\u2013]\s*[\d\u00bd\u00bc\u00be](?:/\d)?){2,3}(?![\d./])"
)

# A line token must be at least this long to count as distinctive on its own.
MIN_DISTINCTIVE_LEN = 4
MIN_SOLO_DISTINCTIVE_LEN = 6
# How close two tokens must be to count as "the same word" for containment.
TOKEN_EQUIVALENCE = 0.9

DOSAGE_FORM_KEYWORDS = [
    "eye drop", "ear drop", "nasal spray", "tablet", "capsule", "syrup",
    "injection", "infusion", "cream", "ointment", "gel", "drops", "drop",
    "lotion", "suspension", "powder", "spray", "inhaler", "solution",
    "sachet", "soap", "shampoo", "lozenge", "patch", "suppository",
    "granules", "emulsion", "paste", "mouthwash", "liquid",
]
DOSAGE_FORM_PATTERNS = [(kw, re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)) for kw in DOSAGE_FORM_KEYWORDS]

# Prescription instruction/frequency words that frequently appear right
# next to a medicine name but aren't part of it (can coincidentally
# string-match an unrelated brand, e.g. "twice" vs "Twicef").
INSTRUCTION_WORDS = {
    "rx", "tab", "tabs", "cap", "caps", "once", "twice", "thrice", "daily",
    "morning", "evening", "night", "afternoon", "before", "after", "food",
    "meals", "meal", "hourly", "weekly", "days", "day", "week", "month",
    "dose", "doses", "take",
    # duration words, including the way they are commonly handwritten ("x 30 dys", "8 wks")
    "dys", "dy", "wks", "wk", "weeks", "months", "month",
    # "for 5 days": the preposition is not part of any name (it looked up brands starting "For...")
    "for",
    # Spelled-out quantities: "days one g" is a dosing fragment, not a name.
    "one", "ones", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "half", "alternate", "continue", "stop",
}

# Ordinary prescription-header/administrative vocabulary. These are common
# English/medical words that describe the DOCUMENT, not a medicine - kept
# as a general class so no single word needs to be hardcoded as a
# one-off exception.
ADMINISTRATIVE_WORDS = {
    "patient", "name", "date", "age", "years", "sex", "gender", "address",
    "prescribed", "prescription", "physician", "doctor", "general",
    "hospital", "clinic", "ward", "consultant", "specialist", "signature",
    "sign", "diagnosis", "complaint", "complaints", "history",
    "examination", "findings", "advice", "follow", "followup", "review",
    "weight", "height", "temperature", "vitals", "regd", "registration",
    "opd", "ipd", "department", "reference", "referred", "note", "notes",
}

# Medical specialty names - a genuine class of words that will always look
# somewhat "medical" to a fuzzy matcher (shared roots with drug/salt
# names) but are never themselves a medicine. Mirrors the specialties
# offered in the frontend's prescription-type step.
MEDICAL_SPECIALTY_WORDS = {
    "cardiology", "cardiologist", "neurology", "neurologist",
    "orthopedics", "orthopedic", "orthopaedics", "orthopaedic",
    "dermatology", "dermatologist", "gynecology", "gynaecology",
    "gynecologist", "pediatrics", "paediatrics", "pediatrician",
    "psychiatry", "psychiatrist", "radiology", "radiologist",
    "pathology", "pathologist", "oncology", "oncologist", "urology",
    "urologist", "nephrology", "nephrologist", "gastroenterology",
    "endocrinology", "endocrinologist", "pulmonology", "pulmonologist",
    "rheumatology", "rheumatologist", "hematology", "haematology",
    "ophthalmology", "ophthalmologist", "otolaryngology", "anesthesiology",
    "anaesthesiology", "anesthesiologist", "dentistry", "dental",
}

NOISE_WORDS = INSTRUCTION_WORDS | ADMINISTRATIVE_WORDS | MEDICAL_SPECIALTY_WORDS

# Words that describe WHERE the clinic is, not what was prescribed. A
# prescription's letterhead is a rich source of false matches because Indian
# place names share syllables with brand names ("Valmiki" -> "Valmip-P").
ADDRESS_WORDS = {
    "road", "street", "circle", "near", "nagar", "layout", "cross", "opp",
    "opposite", "behind", "floor", "building", "complex", "bhavan", "bhavana",
    "colony", "sector", "block", "lane", "marg", "chowk", "landmark", "dist",
    "district", "pincode", "pin", "city", "town", "village", "taluk",
}

# Unlike NOISE_WORDS (which are merely ignored while matching), these mark
# what a whole LINE is for. A line that announces itself as the patient's
# name, the date, a diagnosis or the clinic's address is not a prescription
# line at all, no matter what else it contains.
LINE_DISQUALIFIERS = ADDRESS_WORDS | {
    "diagnosis", "complaint", "complaints", "address", "name", "date", "age",
    "patient", "doctor", "ward", "opd", "ipd", "department", "prescription",
    "sex", "gender", "hospital", "clinic", "consultant", "physician",
    "surgeon", "specialist", "gynecologist", "obstetrician", "registration",
    "regd", "signature", "followup", "review", "mob", "mobile", "phone",
    "email", "www", "reg",
    # Prescriber credentials on the letterhead. Written as abbreviations, so
    # the spelled-out words above never catch them.
    "dr", "drs", "prof", "mbbs", "bds", "md", "ms", "dnb", "dgo", "dch",
    "mrcp", "mrcog", "frcs", "bams", "bhms", "dm", "mch", "kmc", "appointment",
    "queries", "centre", "center",
    # Section headings on the form itself. "Treatment :" was matching the
    # brand "Hairizer Hair Growth Treatment" - a heading inventing a medicine.
    "treatment", "advice", "advise", "advised", "investigation", "investigations", "procedure",
    # Examination shorthand that heads a findings line, never a prescription.
    "cns", "cvs", "nad", "spo", "temperature", "pulse", "respiration",
    "weight", "height", "bp",
}

# A run of digits this long is a PIN code, phone number or registration
# number - never a dose.
LONG_NUMBER_RE = re.compile(r"\d{5,}")

# "M.B.B.S." / "M. D." - two or more single letters joined by dots.
DOTTED_INITIALS_RE = re.compile(r"(?:\b[a-z]\.\s*){2,}")
# "c/o", "h/o", "s/o" - clinical shorthand introducing an observation. The
# separator is whatever OCR made of the slash: "c/o", "c / o", even "c % o".
# The slash is read as all sorts of things - "c/o", "c / o", "c % o", and
# (very often) the letter l or the digit 1: "clo-", "c1o".
CLINICAL_SHORTHAND_RE = re.compile(r"\b[a-z]\s*[/%|\\l1]\s*o\b[-\s]", re.IGNORECASE)
# A reference/phone number jotted as separated digits ("9 1 3 4 3"). A real
# medicine line carries at most a strength and a quantity.
MANY_NUMBERS_RE = re.compile(r"\d+")
MAX_NUMBER_TOKENS = 3
# Words that open a recorded ABSENT finding rather than a prescription.
NEGATION_OPENERS = {"no", "nil", "nad", "denies"}
# Words that open an INSTRUCTION ("Once in a week x 8 weeks", "After food", "Continue for 5 days"),
# never a medicine. It was matched to "Odan Syrup Sweet Orange" because OCR read "8 weeks" as
# "Sweets". Linking the instruction to the medicine above it is a later feature; here it is
# simply not a medicine.
INSTRUCTION_OPENERS = {"once", "twice", "thrice", "daily", "weekly", "every", "after", "before", "continue", "repeat"}

# Individual words making up the dosage-form vocabulary. A form word is real
# information (it corroborates via _form_agreement) but it is not distinctive
# enough to identify a product - almost every candidate ends in one - so it
# must not carry a containment match by itself.
DOSAGE_FORM_TOKENS = {w for kw in DOSAGE_FORM_KEYWORDS for w in kw.split()}


def _build_boolean_query(text):
    words = WORD_RE.findall(text)
    significant = [w for w in words if len(w) >= MIN_WORD_LENGTH and w.lower() not in NOISE_WORDS]
    terms = []
    for word in significant[:MAX_QUERY_WORDS]:
        prefix = word[:WILDCARD_PREFIX_LEN]
        if len(prefix) >= 3:
            terms.append(f"{prefix}*")
    return " ".join(terms)


def _is_document_furniture(text):
    """
    True when the line is part of the prescription's paperwork - letterhead,
    address, patient details, clinical notes - rather than something that
    was prescribed.
    """
    lowered = text.lower()
    # Dotted initialisms first: cloud OCR returns qualifications as
    # "M.B.B.S. , M.D." where the local engine returned "MBBS MD". Split on
    # letters alone that becomes m/b/b/s - single characters that match
    # nothing - so the whole letterhead line sailed into the results table.
    joined = DOTTED_INITIALS_RE.sub(lambda m: m.group(0).replace(".", "").replace(" ", ""), lowered)

    words = set(WORD_RE.findall(joined))
    if words & LINE_DISQUALIFIERS:
        return True
    # Clinical shorthand - "c/o" (complains of), "h/o" (history of),
    # "s/o" (suggestive of). These head an observation, never a medicine.
    if CLINICAL_SHORTHAND_RE.search(text):
        return True
    # A line opening with "no" is the doctor recording an ABSENT finding -
    # "No h/o palpitation", "No other co-morbidities". Nothing is being
    # prescribed. Matched as a whole first word, so a brand that merely
    # starts with those letters ("Nootropil") is unaffected.
    first_word = next(iter(WORD_RE.findall(joined)), "")
    if first_word in NEGATION_OPENERS or first_word in INSTRUCTION_OPENERS:
        return True
    if len(MANY_NUMBERS_RE.findall(_strip_non_name_phrases(text))) > MAX_NUMBER_TOKENS:
        return True
    return bool(LONG_NUMBER_RE.search(text))


def _looks_like_medicine_line(text):
    """
    True when a line could be something the doctor prescribed, even though
    nothing in our database matched it.

    Deliberately generous. On a handwritten prescription the medicine lines
    are exactly the ones OCR mangles worst - "T. Anrue-p" comes back as
    'Aop"u-$' and "zerogod 200" as '2epo4 a00' - so any test demanding a
    readable dose, dosage form or dosing word throws away the very lines the
    user most needs to correct. Requiring those signals dropped 3 of the 4
    medicines off a real prescription.

    What still gets dropped is only what we can positively identify as
    paperwork (see _is_document_furniture) or as too fragmentary to be a
    word at all. Anything else reaches the results table as "Needs
    Verification" with no invented guess attached, for the user to identify.
    """
    if _is_document_furniture(text):
        return False
    # A medicine line has to name SOMETHING. "days one g", "fo & days" and a
    # bare "Tablet" are leftover fragments - every real word in them is
    # dosing or packaging vocabulary, so there is no name to identify.
    # ("Tablet" alone otherwise matched, since every tablet in the catalogue
    # contains the word.)
    return any(
        len(run) >= MIN_SURFACEABLE_RUN
        and run.lower() not in NOISE_WORDS
        and run.lower() not in DOSAGE_FORM_TOKENS
        for run in WORD_RE.findall(text)
    )


def _has_substantive_word(text):
    """
    True when the line contains a word that could be a NAME - not dosing
    vocabulary, not a packaging word, not paperwork.

    Checked before matching, because a line of pure packaging vocabulary
    otherwise matched outright: a bare "Tablet" is contained in every tablet
    in the catalogue, so it scored well against an arbitrary one.
    """
    return any(
        len(run) >= MIN_SURFACEABLE_RUN
        and run.lower() not in NOISE_WORDS
        and run.lower() not in DOSAGE_FORM_TOKENS
        for run in WORD_RE.findall(text)
    )


def _prefix_lookup_words(text):
    """
    The words worth looking up as a brand name: real words only, no
    instruction/administrative/specialty vocabulary, no dosage forms.
    """
    words = WORD_RE.findall(text.lower())
    return [
        w for w in words[:MAX_QUERY_WORDS]
        if len(w) >= MIN_PREFIX_WORD_LENGTH and w not in NOISE_WORDS and w not in DOSAGE_FORM_TOKENS
    ]


def _normalize_for_match(text):
    """
    Puts a name into one canonical form so the SAME product written
    differently compares as the same thing: "Zerodol-P", "Zerodol P",
    "Zerodol - P" and "ZERODOL–P" all become "zerodol p".

    Separators (hyphens, dashes, slashes, dots, brackets) become spaces,
    apostrophes close up rather than split a word, and runs of whitespace
    collapse - which also absorbs the stray spacing OCR sprinkles through
    handwriting.

    This is presentation-only normalisation: letters and digits are never
    altered, added or dropped, so it cannot turn one medicine into another.
    """
    lowered = (text or "").lower()
    for mark in APOSTROPHES:
        lowered = lowered.replace(mark, "")
    return SEPARATOR_RE.sub(" ", lowered).strip()


# "T. Pan-D", "T Lincont 100": doctors write a bare T for tablet. Only as the first word of
# the line (after any list number), so a "T" inside a name is untouched.
LEADING_TABLET_RE = re.compile(r"^\s*t\b\.?\s+(?=\S)", re.IGNORECASE)


def _strip_non_name_phrases(text):
    """
    Removes the bits of a prescription line that are demonstrably not part
    of the medicine's name: the list marker a doctor writes down the margin
    ("1.", "2)") and the course length ("x 5 days", "x 5 d").

    Both leak stray tokens into the comparison. "1. Tab Zerodol-P twice
    daily x 5 d" reduced to "1 zerodol p x 5 d", which scored 0.61 against
    "zerodol p tablet" and broke token coverage - enough to send a
    correctly-identified medicine to Needs Verification, and enough for the
    bare list number alone to pick the WRONG product.

    A strength is never removed: the duration pattern requires a time unit,
    so the 650 in "Dolo 650" is untouched, and the list marker must be
    followed by "." or ")" so a leading dose like "5 ml" survives.
    """
    without_marker = LEADING_TABLET_RE.sub("", LIST_MARKER_RE.sub("", text))
    return SCHEDULE_RE.sub(" ", COURSE_LENGTH_RE.sub(" ", without_marker))


def _clean_for_comparison(text):
    tokens = TOKEN_RE.findall(_strip_non_name_phrases(text).lower())
    kept = [t for t in tokens if t not in NOISE_WORDS]
    return " ".join(kept) if kept else text.lower()


def _without_form_words(normalized):
    """
    A normalised name with its dosage-form words ("tablet", "capsule", "syrup", ...) removed.

    "Rhvtrax 10 Tablet" and "Allegra-M Tablet" share nothing but the last word, yet that word
    alone lifted their name similarity from 0.23 to 0.61, just over the match floor: among
    OCR-corrupted real product names, 86 of 454 automatic matches were a DIFFERENT medicine.
    A form word describes the packaging, not the product, and form is scored on its own
    (_form_agreement), so it must not also count as evidence the NAME is right.
    """
    kept = [w for w in normalized.split() if w not in DOSAGE_FORM_TOKENS]
    return " ".join(kept) if kept else normalized


def _similarity(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _covers_every_token(raw_line, candidate_name, exact=False):
    """
    True when the candidate's name accounts for EVERY meaningful token the
    line wrote - the signal that separates "Zerodol-P Tablet" from
    "Zerodol Gel" when the line said "Zerodol-P".

    Whole-string similarity can't express this: it penalises the correct
    candidate for being longer, so the shorter wrong product wins. Asking
    "does this candidate explain everything the line said?" does not.

    Deliberately strict, so it can only ever promote a BETTER-evidenced
    candidate, never a looser one:
      - numbers must match exactly (650 is not 500),
      - short fragments must match exactly ("P" must not become "PG"),
      - only substantial words may match near-exactly, which is what lets
        "Amoxicillin" reach the dataset's "Amoxycillin".
    """
    # Same stripping as _clean_for_comparison, so coverage and scoring judge
    # the same text. Reading the RAW line here meant a list marker or a
    # course length ("1. ... x 5 d") counted as tokens the candidate had to
    # explain - which no medicine name ever can, silently disabling this
    # signal on exactly the realistic lines it exists to handle.
    stripped = _strip_non_name_phrases(raw_line)
    # Dosing information is not part of a name: "650 SOS", "5 OD", "500 ER", "x 5 days" must not
    # count as words the product has to explain.
    line_tokens = [t for t in _normalize_for_match(stripped).split()
                   if t not in NOISE_WORDS and t not in FREQUENCY_WORDS and t not in _RELEASE_WORDS and t not in _UNIT_WORDS]
    if not line_tokens:
        return False
    candidate_tokens = _normalize_for_match(candidate_name).split()
    if not candidate_tokens:
        return False

    # At least one token has to actually name something. Without this a bare
    # "Tablet" would be "covered" by every tablet in the database.
    if not any(not t.isdigit() and t not in DOSAGE_FORM_TOKENS for t in line_tokens):
        return False

    for token in line_tokens:
        if token in candidate_tokens:
            continue
        if exact or token.isdigit() or len(token) < MIN_DISTINCTIVE_LEN:
            return False
        if not any(_similarity(token, other) >= TOKEN_EQUIVALENCE for other in candidate_tokens):
            return False
    return True


def _distinctive_tokens(cleaned_text):
    """
    The tokens that actually identify a product: real words long enough to
    mean something, plus any numbers. Dosage-form words are excluded - they
    describe the packaging, not the medicine.
    """
    out = []
    for t in TOKEN_RE.findall(cleaned_text.lower()):
        if t.isdigit():
            out.append(t)
        elif len(t) >= MIN_DISTINCTIVE_LEN and t not in NOISE_WORDS and t not in DOSAGE_FORM_TOKENS:
            out.append(t)
    return out


def _containment_signal(cleaned_line, candidate_name):
    """
    Returns 1.0 when everything distinctive the line says is also present in
    the candidate's name, else None (never a penalty).

    This is the signal a whole-string ratio can't express: "Telma 40" IS
    "Telma 40 Tablet", but comparing those two strings end-to-end scores
    badly purely because the candidate is longer. Containment asks the
    question that actually matters - does the candidate account for every
    meaningful thing the line said?

    Deliberately conservative, so it can't resurrect the false-positive
    class this module already guards against: form words and short
    fragments are never distinctive, a lone token must be long AND
    near-exact, and near-exact means near-exact (0.9), so "fever" does not
    silently become "Feveryl".
    """
    line_tokens = _distinctive_tokens(cleaned_line)
    if not line_tokens:
        return None
    if len(line_tokens) == 1:
        solo = line_tokens[0]
        if solo.isdigit() or len(solo) < MIN_SOLO_DISTINCTIVE_LEN:
            return None

    candidate_tokens = TOKEN_RE.findall((candidate_name or "").lower())
    if not candidate_tokens:
        return None

    for token in line_tokens:
        if token in candidate_tokens:
            continue
        if token.isdigit():
            return None  # a number must match exactly - 650 is not 500
        if not any(_similarity(token, ct) >= TOKEN_EQUIVALENCE for ct in candidate_tokens):
            return None
    return 1.0


def _strength_agreement(line_text, candidate_strength):
    """
    Returns 1.0 if the line and the candidate mention the same
    number+unit, 0.0 if they mention DIFFERENT numbers (a real conflict),
    or None if there's nothing to compare (don't penalize or reward).
    """
    if not candidate_strength:
        return None
    cand_match = STRENGTH_RE.search(candidate_strength)
    if not cand_match:
        return None
    cand_num = cand_match.group(1)

    line_text = _strip_non_name_phrases(line_text)
    line_match = STRENGTH_RE.search(line_text)
    if line_match:
        return 1.0 if line_match.group(1) == cand_num else 0.0

    # No unit written on the line - but prescriptions routinely omit it
    # ("Dolo 650", "Telma 40"), and so does OCR. A bare number equal to the
    # candidate's strength is genuine corroboration. It can only ever
    # confirm, never conflict: an unlabelled number could be a quantity or a
    # duration, so it must not disqualify an otherwise good candidate.
    if any(n == cand_num for n in BARE_NUMBER_RE.findall(line_text)):
        return 1.0
    return None


SLASH_PAIR_RE = re.compile(
    r"(?<![\d/])(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(?![\d/]|\s*(?:ml|mg|mcg|g|gm)\b)", re.IGNORECASE
)
PER_VOLUME_RE = re.compile(r"/\s*\d+(?:\.\d+)?\s*ml", re.IGNORECASE)


def _combination_strength_agreement(line_text, candidate):
    """
    Strength agreement that looks at EVERY active ingredient of the candidate.

    The Medicines.strength column holds only the first ingredient's strength,
    so comparing a line against it alone let "Amoxicillin 125 + Clavulanic
    acid 62.5" agree with a 500/125 product, and made "Augmentin 625" look like
    a strength conflict (the candidate's first strength is 500).

      - a strength written with a unit must be one of the candidate's
        ingredient strengths, otherwise it is a conflict (0.0);
      - when a line states two or more different strengths and the candidate
        is a combination, ALL of them must be present;
      - an "a/b" pair without units (500/125) is judged the same way, but only
        when at least one of its numbers matches (otherwise it is probably a
        date or a dose such as 1/2, and says nothing);
      - an unlabelled number can confirm but never conflict, as before.

    Returns 1.0 / 0.0 / None like _strength_agreement, and falls back to it
    when the composition cannot be read.
    """
    numerators = ingredient_numerators(candidate.get("composition"))
    if not numerators:
        return _strength_agreement(line_text, candidate.get("strength"))
    wanted = set(numerators)
    is_combo = len(numerators) >= 2

    flat = PER_VOLUME_RE.sub("", _strip_non_name_phrases(line_text))
    unit_numbers = [canonical_number(n) for n, _ in STRENGTH_RE.findall(flat)]
    if unit_numbers:
        if unit_numbers[0] not in wanted:
            return 0.0
        if is_combo and len(set(unit_numbers)) >= 2 and not all(n in wanted for n in unit_numbers):
            return 0.0
        return 1.0

    if is_combo:
        for a, b in SLASH_PAIR_RE.findall(flat):
            pair = [canonical_number(a), canonical_number(b)]
            if any(n in wanted for n in pair):
                return 1.0 if all(n in wanted for n in pair) else 0.0

    # An unlabelled number is read as the product's own strength: its first ingredient's, or a
    # number written in its name ("Augmentin 625"). Matching a LATER ingredient's strength
    # proves nothing about which product was meant (500 is calcium carbonate in a calcitriol
    # capsule, and "Shelcal 500" is not that capsule).
    name_numbers = {canonical_number(n) for n in BARE_NUMBER_RE.findall(candidate.get("medicine_name") or "")}
    own = {numerators[0]} | name_numbers
    if any(canonical_number(n) in own for n in BARE_NUMBER_RE.findall(flat)):
        return 1.0
    return None


NUMBER_OR_WORD_RE = re.compile(r"\d+(?:\.\d+)?|[A-Za-z]+")
# Words that may sit between an ingredient name and its strength ("clavulanic ACID 125").
STRENGTH_GAP_WORDS = {"acid", "mg", "mcg", "gm", "ml", "and", "with", "tab", "tablet", "of"}
# A number followed by one of these is a dose count or duration, not a strength.
NOT_A_STRENGTH_AFTER = {"day", "days", "d", "tab", "tabs", "tablet", "tablets", "cap", "caps", "times", "x", "weeks", "week", "wk", "wks"}
# Dosing frequency. "Paracetamol 650 BD" is a 650 strength twice a day, while "Paracetamol 1 TDS"
# is one tablet three times a day: after a frequency word a small whole number is a count, not a strength.
FREQUENCY_WORDS = {"od", "bd", "bid", "tds", "tid", "qid", "qd", "hs", "sos", "stat", "daily", "once", "twice", "thrice"}
MAX_TABLET_COUNT = 3


def _stated_ingredient_strengths(raw_line, named_ingredients):
    """
    {ingredient: number} for every named ingredient that has a number written
    right after it: "Amoxicillin 500 + Clavulanic acid 125" gives
    {amoxycillin: '500', clavulanic acid: '125'}. This is what lets a combination
    line be checked ingredient by ingredient instead of against a single number.
    """
    tokens = NUMBER_OR_WORD_RE.findall(raw_line)
    lowered = [t.lower() for t in tokens]
    stated = {}
    for salt in named_ingredients:
        word = _distinctive_word(salt)
        for i, tok in enumerate(lowered):
            if tok.isdigit() or not (tok == word or _similarity(word, tok) >= TOKEN_EQUIVALENCE):
                continue
            for j in range(i + 1, min(i + 4, len(tokens))):
                nxt = lowered[j]
                if nxt[0].isdigit():
                    after = lowered[j + 1] if j + 1 < len(tokens) else ""
                    is_count = after in FREQUENCY_WORDS and "." not in tokens[j] and int(float(tokens[j])) <= MAX_TABLET_COUNT
                    if after not in NOT_A_STRENGTH_AFTER and not is_count:
                        stated[salt] = canonical_number(tokens[j])
                    break
                if nxt not in STRENGTH_GAP_WORDS:
                    break
            break
    return stated


def _per_ingredient_agreement(raw_line, candidate, named_ingredients):
    """
    Compare each ingredient's strength with the number the line wrote right after
    that ingredient's name. 0.0 if any differs, 1.0 if every stated one matches,
    None when the line states no per-ingredient strength.

    Applies to single-ingredient products too: "Nifedipine 30" states a strength
    even without a unit, so a 5, 10 or 20 mg product is a conflict rather than a
    near match. (A number that follows a BRAND name - "Dolo 650" - is not an
    ingredient strength and is never looked at here.)
    """
    ingredients = split_ingredients(candidate.get("composition"))
    if not ingredients or not named_ingredients:
        return None
    stated = _stated_ingredient_strengths(raw_line, named_ingredients)
    if not stated:
        return None
    checked = 0
    for salt, number in stated.items():
        word = _distinctive_word(salt)
        for name, numbers in ingredients:
            if numbers and (word == _distinctive_word(name) or _similarity(word, _distinctive_word(name)) >= 0.85):
                checked += 1
                if numbers[0] != number:
                    return 0.0
                break
    return 1.0 if checked else None


def _form_agreement(line_text, candidate_form):
    """
    Same idea as strength agreement, for dosage form: 1.0 if the line
    mentions a dosage-form word that matches the candidate's recorded
    form, 0.0 if it mentions a DIFFERENT one, None if the line doesn't
    mention a form at all.
    """
    if not candidate_form:
        return None
    line_lower = line_text.lower()
    mentioned = None
    for kw, pattern in DOSAGE_FORM_PATTERNS:
        if pattern.search(line_lower):
            mentioned = kw
            break
    if mentioned is None:
        return None
    return 1.0 if _form_matches(mentioned, candidate_form) else 0.0


# Prescription shorthand for the dosage form, which almost every real
# prescription uses instead of the full word ("Tab Dolo", "Syp Ascoril").
FORM_ABBREVIATIONS = {
    "tab": "tablet", "tabs": "tablet", "cap": "capsule", "caps": "capsule",
    "syp": "syrup", "syr": "syrup", "susp": "suspension", "inj": "injection",
    "oint": "ointment", "cr": "cream",
}
FORM_ABBREVIATION_RE = re.compile(r"\b(" + "|".join(FORM_ABBREVIATIONS) + r")\b\.?", re.IGNORECASE)

# How much a form mismatch / unmentioned extra salt costs a candidate.
# Penalties rather than disqualifications: a prescription's "Tab" is a strong
# hint, not a guarantee, and the dataset's form labels are not always tidy.
FORM_MISMATCH_PENALTY = 0.15
EXTRA_SALT_PENALTY = 0.15
# Candidates this close to the winner count as "strong" alternatives.
DISAMBIGUATION_MARGIN = 0.04
MAX_OPTIONS = 3


def _form_matches(mentioned, candidate_form):
    """
    Whether a mentioned form word fits a recorded form. Containment, not
    equality: the dataset has "Tablet SR", "Eye Drops", "Capsule SR", and a
    prescription that says "tablet" is not contradicted by those.
    """
    recorded = (candidate_form or "").strip().lower()
    return bool(recorded) and mentioned.rstrip("s") in recorded


def _inferred_form(line_text):
    """The form implied by shorthand ("Tab" -> tablet, a leading "T." -> tablet), or None."""
    match = FORM_ABBREVIATION_RE.search(line_text or "")
    if match:
        return FORM_ABBREVIATIONS[match.group(1).lower()]
    if LEADING_TABLET_RE.match(LIST_MARKER_RE.sub("", line_text or "")):
        return "tablet"
    return None


def _explicit_form_word(line_text):
    lowered = (line_text or "").lower()
    return any(pattern.search(lowered) for _, pattern in DOSAGE_FORM_PATTERNS)


def _soft_form_signal(line_text, candidate_form):
    """
    1.0 / 0.0 when the line implies a form only through shorthand and the
    candidate does / doesn't have it; None when the form was spelled out
    (the strict check owns that case) or isn't mentioned at all.
    """
    if not candidate_form or _explicit_form_word(line_text):
        return None
    inferred = _inferred_form(line_text)
    if not inferred:
        return None
    return 1.0 if _form_matches(inferred, candidate_form) else 0.0


def _form_mismatch(line_text, candidate_form):
    """True when the line implies a form (spelled out or abbreviated) the candidate lacks."""
    return _form_agreement(line_text, candidate_form) == 0.0 or _soft_form_signal(line_text, candidate_form) == 0.0


def _candidate_salts(candidate):
    """The active ingredients of a candidate, as lowercase names without strengths."""
    composition = candidate.get("composition") or ""
    if "+" in composition:
        parts = re.split(r"\s*\+\s*", composition)
    else:
        parts = [candidate.get("primary_salt"), candidate.get("secondary_salt")]
    names = []
    for part in parts:
        cleaned = re.sub(r"\(.*?\)", "", part or "").strip().lower()
        if cleaned and cleaned not in names:
            names.append(cleaned)
    return names


def _salt_mentioned(salt_name, line_tokens):
    words = [w for w in re.findall(r"[a-z]+", salt_name) if len(w) >= MIN_DISTINCTIVE_LEN]
    if not words:
        return True  # nothing distinctive to look for - don't count it as extra
    return any(
        w in line_tokens or any(_similarity(w, t) >= TOKEN_EQUIVALENCE for t in line_tokens)
        for w in words
    )


def _unmentioned_extra_salts(raw_line, candidate):
    """
    Active ingredients the candidate contains that the line never wrote -
    but only when the line DID name at least one of its salts. A line that
    says "Amoxicillin" describes a single-ingredient product; the same
    product plus clavulanic acid is a different medicine, however close the
    names look. When none of the salts are mentioned the line is a brand
    name, and brand lines are judged by name coverage instead.
    """
    salts = _candidate_salts(candidate)
    if len(salts) < 2:
        return []
    line_tokens = [t for t in _normalize_for_match(_strip_non_name_phrases(raw_line)).split() if not t.isdigit()]
    mentioned = [s for s in salts if _salt_mentioned(s, line_tokens)]
    if not mentioned or len(mentioned) == len(salts):
        return []
    return [s for s in salts if s not in mentioned]


def _is_unmentioned_combination(raw_line, candidate):
    """
    A combination product the line did not ask for.

    A line that names one of the product's ingredients but not the rest is
    asking for a single-ingredient medicine. This used to be waved through
    whenever the product's NAME happened to contain every word of the line, so
    "Metformin 500mg" matched "Metformin + Vildagliptin 500mg/50mg Tablet". A
    line that names no ingredient at all is a brand ("Zerodol-P"), and
    _unmentioned_extra_salts already treats that as not-a-combination-request.
    """
    return bool(_unmentioned_extra_salts(raw_line, candidate))


def _distinctive_word(salt_name):
    """The longest word of an ingredient name - the part that identifies it."""
    words = re.findall(r"[a-z]+", salt_name)
    return max(words, key=len) if words else ""


def _salt_named_in_line(salt_name, line_tokens):
    word = _distinctive_word(salt_name)
    if len(word) < MIN_DISTINCTIVE_LEN + 1:
        return False
    return any(word == t or _similarity(word, t) >= TOKEN_EQUIVALENCE for t in line_tokens)


def _candidate_has_salt(candidate_salts, named_salt):
    word = _distinctive_word(named_salt)
    return any(
        word == _distinctive_word(cs) or _similarity(word, _distinctive_word(cs)) >= 0.85
        for cs in candidate_salts
    )


def _named_ingredients(raw_line, candidates):
    """
    Ingredients the line itself names, found by looking for the ingredient names
    of the retrieved candidates in the line's words. ("Amoxicillin + Clavulanic
    acid" names both; "Dolo 650" names none.)
    """
    line_tokens = [t for t in _normalize_for_match(_strip_non_name_phrases(raw_line)).split() if not t.isdigit()]
    pool = set()
    for c in candidates:
        pool.update(_candidate_salts(c))
    return [s for s in pool if _salt_named_in_line(s, line_tokens)]


def _missing_named_ingredients(candidate, named):
    """Ingredients the line names that this candidate does not contain."""
    if not named:
        return []
    have = _candidate_salts(candidate)
    return [s for s in named if not _candidate_has_salt(have, s)]


def _cannot_be_verified(raw_line, candidate):
    """
    Why this candidate must never be settled automatically, however well its name scores - or None.

    These are the cases where the dataset itself cannot back the match, so confidence is beside
    the point and a person has to decide:
      - its ingredient list is known to be incomplete (the source CSV holds two ingredient columns,
        so a third was lost): "Rosuvastatin 10 + Aspirin 150" is NOT "Aspirin + Rosuvastatin +
        Clopidogrel", whose composition reads as exactly that pair;
      - it contains an ingredient the line never named: "Levosulpiride 75" is not "Levosulpiride +
        Esomeprazole" (a line that names no ingredient at all is a brand, and is not judged here);
      - an ingredient has no strength on record ("Metformin (NA)") while the line writes a number
        the product's name does not carry: nothing can be compared, so no strength can agree.
    """
    if candidate.get("composition_incomplete"):
        return "incomplete ingredient list"
    if _unmentioned_extra_salts(raw_line, candidate):
        return "contains ingredients the line does not name"
    if has_unknown_strength(candidate.get("composition")):
        flat = PER_VOLUME_RE.sub("", _strip_non_name_phrases(raw_line))
        written = {canonical_number(n) for n in BARE_NUMBER_RE.findall(flat)}
        in_name = {canonical_number(n) for n in BARE_NUMBER_RE.findall(candidate.get("medicine_name") or "")}
        if written - in_name:
            return "strength not on record"
    return None


def _settles_automatically(raw_line, score, candidate, named_ingredients):
    """
    May this candidate be presented as a settled match? Never when the dataset cannot back it
    (_cannot_be_verified). Otherwise only with real identity evidence - every word of the line
    found in its name, or every ingredient the line names present and nothing unnamed - or a
    confidence high enough that look-alike mistakes are rare (see AUTO_MATCH_MIN_CONFIDENCE).
    Anything else is only a guess for the person to confirm.
    """
    if _cannot_be_verified(raw_line, candidate):
        return False
    if score >= AUTO_MATCH_MIN_CONFIDENCE:
        return True
    # Only EXACT words count here: "serrta" is 91% similar to "serra", yet they are two different
    # brands. (Near-equal spellings still help ranking elsewhere; they just cannot settle a line.)
    if _covers_every_token(raw_line, candidate["medicine_name"], exact=True):
        return True
    # A line that names only ingredients is identified by them: the candidate contains what was
    # named (and, being filtered earlier, nothing the line did not name).
    if is_generic_line(raw_line, candidate) and not _missing_named_ingredients(candidate, named_ingredients):
        return True
    return bool(
        named_ingredients and len(_candidate_salts(candidate)) >= 2
        and not _missing_named_ingredients(candidate, named_ingredients)
        and not _unmentioned_extra_salts(raw_line, candidate)
    )


def _signature(candidate):
    """What makes two catalogue entries genuinely different medicines."""
    def norm(value):
        return _normalize_for_match(value or "")
    return (norm(candidate.get("primary_salt")), norm(candidate.get("secondary_salt")),
            norm(candidate.get("strength")), norm(candidate.get("form")),
            candidate.get("release_type"), composition_key(candidate.get("composition")))


def _option_entry(score, candidate):
    return {
        "medicine_id": candidate["medicine_id"],
        "medicine_name": candidate["medicine_name"],
        "strength": candidate.get("strength"),
        "form": candidate.get("form"),
        "manufacturer": candidate.get("manufacturer"),
        "release_type": candidate.get("release_type"),
        "composition": candidate.get("composition"),
        "score": round(score, 4),
    }


# Words that may appear on a generic-name line without being a brand: release
# markers, dosage-form shorthand, units, and the salt suffix of an ingredient name.
_RELEASE_WORDS = {"sr", "er", "xr", "xl", "cr", "pr", "dt", "odt", "md", "sustained", "release", "extended",
                  "controlled", "prolonged", "modified", "retard", "chewable"}
_SALT_SUFFIX_WORDS = {"hydrochloride", "hcl", "sodium", "potassium", "calcium", "sulphate", "sulfate", "phosphate",
                      "maleate", "tartrate", "besylate", "succinate", "mesylate", "acetate", "citrate"}
_GENERIC_IGNORED = (NOISE_WORDS | DOSAGE_FORM_TOKENS | _RELEASE_WORDS | _SALT_SUFFIX_WORDS | set(FORM_ABBREVIATIONS)
                    | {"mg", "mcg", "gm", "gms", "ml", "iu", "and", "with", "plus", "of", "oral", "w", "v"}
                    | NOT_A_STRENGTH_AFTER | FREQUENCY_WORDS)

MAX_VARIANT_OPTIONS = 6
_UNIT_WORDS = {"mg", "mcg", "gm", "gms", "ml", "iu", "x"}


def is_generic_line(raw_line, candidate):
    """
    True when the line names only ingredients ("Metformin 500 SR",
    "Amoxicillin + Clavulanic acid", "Syp Paracetamol") and no brand. Such a line
    means "any product with this composition", so the specific brand the matcher
    attaches to it is a representative, not what the doctor wrote. Pure function of
    the line and the matched product, so it can be re-derived wherever it is needed.
    """
    salt_words = {w for salt in _candidate_salts(candidate) for w in re.findall(r"[a-z]+", salt)}
    if not salt_words:
        return False
    tokens = [t for t in _normalize_for_match(_strip_non_name_phrases(raw_line or "")).split()
              if t.isalpha() and t not in _GENERIC_IGNORED]
    if not tokens:
        return False
    return all(any(t == w or _similarity(t, w) >= TOKEN_EQUIVALENCE for w in salt_words) for t in tokens)


def _variant_key(candidate):
    """
    What makes two products different MEDICINES (not just different brands): the
    ingredients, each ingredient's strength NUMBER, the dosage form and the release
    type. The unit is left out on purpose: the dataset has typos such as
    "Amoxycillin (500mcg) + Clavulanic Acid (125mg)" on a product named "625", and
    treating that as a separate medicine would make a clearly specified line
    "ambiguous". Such rows are reported by the data audit, not silently corrected.
    """
    strengths = tuple(
        (_distinctive_word(name), numbers[0] if numbers else None)
        for name, numbers in split_ingredients(candidate.get("composition"))
    )
    return (strengths, _normalize_for_match(candidate.get("form") or ""), candidate.get("release_type"))


def _ingredient_set(candidate):
    return frozenset(_distinctive_word(name) for name, _ in split_ingredients(candidate.get("composition")))


def _first_strength(candidate):
    numbers = ingredient_numerators(candidate.get("composition"))
    return float(numbers[0]) if numbers else 0.0


def _ambiguous_variants(raw_line, cleaned_line, best, best_score, eligible, named_ingredients, line_release):
    """
    When the line does not say which strength / dosage form / release type was meant
    and the dataset holds several, returns those variants as option entries
    (one representative product each); otherwise None. Returns (options, resolved, preferred):
    `resolved` is True for a generic line whose stated details left exactly one
    medicine, so brand-level "close matches" are noise and should not be shown;
    `preferred` is then (score, product) for that one medicine, which the caller uses when the
    text-search candidates did not include it (an unmarked "Diltiazem 180" must be the
    immediate-release tablet the dataset has, not the extended-release capsule that happened to
    rank first).

    Silently picking one is a guess about a dose. This is what stops
    "Metformin" becoming a 500 mg tablet and "Syp Paracetamol" a paediatric
    250 mg suspension: the line's own statements (strength, form, "SR") have
    already ruled products out, and if more than one medicine is still left the
    line is under-specified and a person must choose.
    """
    members = {}
    popularity = {}

    def add(score, candidate):
        key = _variant_key(candidate)
        count = candidate.get("product_count", 1)
        popularity[key] = popularity.get(key, 0) + count
        # Of several products sharing one variant, show the one written the way most
        # products are (so the common unit wins over a typo), then the best scorer.
        if key not in members or (count, score) > (members[key][2], members[key][0]):
            members[key] = (score, candidate, count)

    def usable(candidate):
        """A variant that cannot be told apart from the line is not a real option."""
        if candidate.get("composition_incomplete"):
            return False  # its real ingredients are unknown
        if not ingredient_numerators(candidate.get("composition")):
            return False  # no strength on record: it could be any strength
        if not (candidate.get("form") or "").strip():
            return False  # form unknown: cannot tell which of the variants it is
        return True

    best_covers = _covers_every_token(raw_line, best["medicine_name"])
    for score, _, _, candidate in eligible:
        # A line whose every word is found in the product name identifies a brand
        # (or an ingredient): every product that name covers is a possibility, however
        # its score compares - "Augmentin" must not be settled by "Augmentin 375"
        # merely scoring a point higher than "Augmentin 625 Duo".
        if not best_covers and score < best_score - DISAMBIGUATION_MARGIN:
            continue
        if _covers_every_token(raw_line, candidate["medicine_name"]) != best_covers:
            continue
        if _form_mismatch(raw_line, candidate["form"]):
            continue
        if usable(candidate):
            add(score, candidate)

    # A generic line is not tied to any brand, so the candidate list (a handful of
    # relevance hits) is not the full picture: ask the dataset what else exists.
    if is_generic_line(raw_line, best):
        for candidate in get_family_variants(best.get("primary_salt"), best.get("secondary_salt")):
            score, _threshold, disqualified = _score_candidate(
                raw_line, cleaned_line, candidate, named_ingredients=named_ingredients, line_release=line_release
            )
            if disqualified or _form_mismatch(raw_line, candidate["form"]) or _is_unmentioned_combination(raw_line, candidate):
                continue
            if usable(candidate):
                add(score, candidate)

    wanted = _ingredient_set(best)
    same = {k: v for k, v in members.items() if _ingredient_set(v[1]) == wanted}
    # No release type stated: a conventional product is what is meant, as long as one exists.
    if not line_release and any(k[2] is None for k in same):
        same = {k: v for k, v in same.items() if k[2] is None}
    if len(same) < 2:
        generic = is_generic_line(raw_line, best)
        only = next(iter(same.values())) if (generic and same) else None
        return None, generic, ((only[0], only[1]) if only else None)

    # Show the variants the dataset has most products for (so 500 and 650 are not
    # hidden behind a dozen rare strengths), then list them in a readable order.
    common = sorted(same.items(), key=lambda kv: (-popularity.get(kv[0], 0), kv[1][1]["medicine_id"]))[:MAX_VARIANT_OPTIONS]
    ordered = sorted((v[:2] for _, v in common), key=lambda sv: (sv[1].get("release_type") is not None,
                                                            "tablet" not in (sv[1].get("form") or "").lower(),
                                                            _first_strength(sv[1]), sv[1]["medicine_id"]))
    return [_option_entry(score, candidate) for score, candidate in ordered], False, None


def _unexplained_numbers(raw_line, candidate):
    """
    The numbers (two or more digits, no unit) the line writes that this product does not own: not
    its first ingredient's strength and not a number in its name. Empty when the line writes no
    such number, or when the product owns at least one of them.
    """
    flat = PER_VOLUME_RE.sub("", _strip_non_name_phrases(raw_line))
    written = {canonical_number(n) for n in BARE_NUMBER_RE.findall(flat) if len(n.split(".")[0]) >= 2}
    # a number carrying a unit is judged by the strength check, not here
    written -= {canonical_number(n) for n, _ in STRENGTH_RE.findall(flat)}
    if not written:
        return []
    numerators = ingredient_numerators(candidate.get("composition"))
    own = set(numerators[:1]) | {canonical_number(n) for n in BARE_NUMBER_RE.findall(candidate.get("medicine_name") or "")}
    strength = STRENGTH_RE.search(candidate.get("strength") or "")
    if strength:
        own.add(canonical_number(strength.group(1)))
    return [] if (written & own) else sorted(written)


def _unexplained_number(raw_line, candidate):
    """
    True when the line writes a number (two or more digits, no unit) that this product does not
    own: not its first ingredient's strength and not a number in its name. "Shelcal 500" against
    "Sheltral 400" is the case: the number is the line's strongest clue, and it points elsewhere.
    Only meaningful for a candidate chosen on name similarity alone; a brand the line spells out
    in full explains its own numbers.
    """
    return bool(_unexplained_numbers(raw_line, candidate))


def _score_candidate(raw_line, cleaned_line, candidate, named_ingredients=None, line_release=None):
    """
    Returns (final_score, disqualified) where disqualified=True means a
    confirmed strength or form conflict makes this candidate ineligible
    for a "matched" verdict no matter how high the text similarity is.
    """
    # Compare like with like: the line arrives already broken into tokens,
    # so the candidate is normalised the same way. Comparing a tokenised
    # line against a raw name made punctuation look like a difference -
    # "zerodol p" scored WORSE against "Zerodol-P Tablet" than against the
    # unrelated "Zerodol Gel" purely because of the hyphen.
    line_for_names = _without_form_words(cleaned_line)
    name_score = _similarity(line_for_names, _without_form_words(_normalize_for_match(candidate["medicine_name"])))
    salt_score = _similarity(line_for_names, _without_form_words(_normalize_for_match(candidate["primary_salt"] or "")))
    text_score = max(name_score, salt_score)

    strength_signal = _combination_strength_agreement(raw_line, candidate)
    # When the line writes a strength after each ingredient, that per-ingredient
    # comparison is the more precise evidence and replaces the single-number one.
    per_ingredient = _per_ingredient_agreement(raw_line, candidate, named_ingredients)
    if per_ingredient is not None:
        strength_signal = per_ingredient
    form_signal = _form_agreement(raw_line, candidate["form"])
    containment_signal = _containment_signal(cleaned_line, candidate["medicine_name"])
    # Full coverage is evidence in its own right, not just a tie-break. A
    # short hyphenated brand has no token long enough to be "distinctive"
    # ("Pan-D" is pan + d), so containment stays silent and the name scores
    # badly against the longer catalogue entry - leaving a product that IS
    # in the database unmatched. Explaining every token the line wrote is
    # exactly the evidence that case has.
    coverage_signal = 1.0 if _covers_every_token(raw_line, candidate["medicine_name"]) else None

    # Shorthand ("Tab", "Cap", "Syp") is weaker evidence than a spelled-out
    # form, so it agrees/penalises rather than disqualifying.
    soft_form_signal = _soft_form_signal(raw_line, candidate["form"])

    # A combination whose every ingredient the line names - and which has no
    # ingredient the line did not name - is identified by its ingredients even
    # when its brand name looks nothing like the line ("Amoxicillin +
    # Clavulanic acid" vs "Amoxilin CV 500mg/125mg Tablet"). Only for
    # multi-ingredient products, so single-ingredient scoring is unchanged.
    ingredient_signal = None
    if (
        named_ingredients and len(_candidate_salts(candidate)) >= 2
        and not _missing_named_ingredients(candidate, named_ingredients)
        and not _unmentioned_extra_salts(raw_line, candidate)
    ):
        ingredient_signal = 1.0

    disqualified = strength_signal == 0.0 or form_signal == 0.0

    # An ingredient the line writes out that this product does not contain
    # ("Amoxicillin + Clavulanic acid" vs plain amoxycillin) is a different medicine.
    if _missing_named_ingredients(candidate, named_ingredients):
        disqualified = True

    # A release mechanism the line writes ("... SR") must be the product's own.
    # A conventional tablet and a sustained-release one share salt, strength and
    # form, but are not interchangeable.
    if line_release and candidate.get("release_type") != line_release:
        disqualified = True

    # Real evidence of WHICH product was meant (as opposed to a number or a dosage form that many
    # products share): every word of the line in the name, a distinctive word in it, or every
    # named ingredient present.
    has_identity = any(s is not None and s > 0 for s in (containment_signal, coverage_signal, ingredient_signal))
    if not has_identity and _unexplained_number(raw_line, candidate):
        disqualified = True

    corroborators = [
        s for s in (strength_signal, form_signal, soft_form_signal, containment_signal, coverage_signal, ingredient_signal)
        if s is not None and s > 0
    ]
    if corroborators:
        corroboration = sum(corroborators) / len(corroborators)
        final_score = text_score * 0.6 + corroboration * 0.4
        threshold = MATCH_THRESHOLD_CORROBORATED
        if not has_identity and text_score < MIN_NAME_SIMILARITY_WITHOUT_IDENTITY:
            threshold = 1.01  # cannot be matched; still scored, so it can be offered as a closest guess
    else:
        final_score = text_score
        threshold = MATCH_THRESHOLD_TEXT_ONLY

    if soft_form_signal == 0.0:
        final_score -= FORM_MISMATCH_PENALTY
    # A combination product the line didn't ask for costs points: "Amoxicillin"
    # should not drift to amoxycillin + clavulanic acid because the names look alike.
    if _unmentioned_extra_salts(raw_line, candidate):
        final_score -= EXTRA_SALT_PENALTY

    return final_score, threshold, disqualified


def _unidentified_or_skipped(raw_text):
    """
    Nothing in the database was close enough to name. If the line still
    reads like a prescribed item, report it WITHOUT a medicine so the user
    can identify it themselves; otherwise drop it.
    """
    if _looks_like_medicine_line(raw_text):
        return {"raw_text": raw_text, "status": "needs_verification", "confidence": None, "medicine": None}
    return {"raw_text": raw_text, "status": "skipped", "confidence": None, "medicine": None}


def _written_form(raw_line):
    """The dosage form the line says or implies ("tablet" for "Tab" or a leading "T."), or None."""
    lowered = (raw_line or "").lower()
    for keyword, pattern in DOSAGE_FORM_PATTERNS:
        if pattern.search(lowered):
            return keyword
    return _inferred_form(raw_line)


def form_conflict_text(raw_line, candidate_form):
    """
    A plain-language sentence when the line says (or implies, by "Tab" / "Cap" / a leading "T.") a dosage form the
    product does not have, else None. Used to flag an automatic match for a second look; it never changes a match.
    """
    if not _form_mismatch(raw_line, candidate_form):
        return None
    return f"the prescription points to a {_written_form(raw_line)} but the matched product is a {(candidate_form or 'different form').lower()}"


def _guess_reasons(raw_line, score, candidate):
    """
    Why a closest guess was NOT accepted on its own, in plain language, worked out from the same
    rules that decided it (see _settles_automatically). The list is never empty for a guess that
    reaches the person: a guess is only ever offered because one of these held.
    """
    reasons = []
    blocked = _cannot_be_verified(raw_line, candidate)
    if blocked == "incomplete ingredient list":
        reasons.append("The dataset's ingredient list for this product is incomplete, so it cannot be checked against the line.")
    elif blocked == "contains ingredients the line does not name":
        reasons.append("This product contains ingredients the line does not name.")
    elif blocked == "strength not on record":
        reasons.append("This product has no strength on record, so the number written cannot be compared.")
    if not _covers_every_token(raw_line, candidate["medicine_name"], exact=True):
        reasons.append("The name as read is only similar to this product, not the same. The text may have been misread, "
                       "or the brand may not be in the dataset.")
        if score < AUTO_MATCH_MIN_CONFIDENCE:
            reasons.append(f"The similarity ({percent(score)}%) is below the {percent(AUTO_MATCH_MIN_CONFIDENCE)}% "
                           "needed to accept a look-alike without a person checking.")
    if _form_mismatch(raw_line, candidate.get("form")):
        reasons.append(f"The line points to a {_written_form(raw_line)} but this product is a {(candidate.get('form') or 'different form').lower()}.")
    return reasons


def name_matches_exactly(raw_text, candidate_name):
    """
    True when every meaningful word the line wrote is a word of the product's name, exactly (schedule digits such as the "100" of a
    handwritten 1-0-0 are ignored). This is what separates a SUGGESTION (the written name is this brand's name; strength and form still
    need a person) from a look-alike (a different name that merely scores well): it is never used to accept a match.
    """
    text, _digits = _without_schedule_digits(raw_text)
    return _covers_every_token(text, candidate_name, exact=True)


def _closest_guesses(raw_line, ranked_rows):
    """
    Up to MAX_OPTIONS look-alike products for a line that could not be settled, best first, each
    with the reasons it was not accepted. Never confirmed: these are only what the person is shown.
    """
    guesses, seen = [], set()
    for score, _threshold, _disqualified, candidate in ranked_rows:
        if score < MIN_GUESS_SCORE:
            break
        key = (_normalize_for_match(candidate["medicine_name"]), composition_key(candidate.get("composition")))
        if key in seen:
            continue
        seen.add(key)
        entry = _option_entry(score, candidate)
        entry["reasons"] = _guess_reasons(raw_line, score, candidate)
        guesses.append(entry)
        if len(guesses) >= MAX_OPTIONS:
            break
    return guesses


_SCHEDULE_LOOKALIKE_RE = re.compile(r"^(?=.*1)[01]{3}$")

# The text a line carries when a person added the medicine by hand: it is not something read from a prescription.
MANUAL_ENTRY_TEXT = "Added manually"


def assess_confirmation(raw_text, medicine):
    """
    What a person should know before confirming that the line `raw_text` is the product `medicine`.

    Returns a list of {"code", "severity", "text"}; severity "conflict" is a clear mismatch between what
    the line says and the chosen product (the person must acknowledge it to go ahead), "note" is
    information only. It reuses the matcher's own evidence (name, form, strength, ingredients, release
    type) and invents no new threshold. An empty list means nothing on the line contradicts the choice
    - that is NOT a statement that the product is the right one or medically equivalent: only the person
    holding the prescription can say that.
    """
    if not raw_text or raw_text.strip().lower() == MANUAL_ENTRY_TEXT.lower() or not _has_substantive_word(raw_text):
        return []
    name = medicine.get("medicine_name") or "this product"
    findings = []

    def add(code, severity, text):
        findings.append({"code": code, "severity": severity, "text": text})

    cleaned = _clean_for_comparison(raw_text)
    query = _build_boolean_query(raw_text)
    pool = [medicine] + (search_candidates(query) if query else [])
    named = _named_ingredients(raw_text, pool)

    # name
    exact = _covers_every_token(raw_text, medicine["medicine_name"], exact=True)
    ingredient_only = is_generic_line(raw_text, medicine) and not _missing_named_ingredients(medicine, named)
    if not exact and not ingredient_only:
        line_for_names = _without_form_words(cleaned)
        similarity = max(
            _similarity(line_for_names, _without_form_words(_normalize_for_match(medicine["medicine_name"]))),
            _similarity(line_for_names, _without_form_words(_normalize_for_match(medicine.get("primary_salt") or ""))),
        )
        if similarity < MIN_NAME_SIMILARITY_WITHOUT_IDENTITY:
            add("name", "conflict", f"The prescription line reads “{raw_text}”, which does not look like “{name}”. "
                                    "If the line was misread, check the original prescription.")
        else:
            add("name", "note", f"The name on the line is only similar to “{name}”, not the same.")

    # dosage form
    if _form_mismatch(raw_text, medicine.get("form")):
        add("form", "conflict", f"The prescription line points to a {_written_form(raw_text)}, but “{name}” is a "
                                f"{(medicine.get('form') or 'different form').lower()}.")

    # strength, per ingredient where the line gives one
    strength_signal = _combination_strength_agreement(raw_text, medicine)
    per_ingredient = _per_ingredient_agreement(raw_text, medicine, named)
    if per_ingredient is not None:
        strength_signal = per_ingredient
    if strength_signal == 0.0:
        add("strength", "conflict", f"The strength written on the line does not match “{name}” "
                                    f"({medicine.get('strength') or 'strength not on record'}).")

    # an ingredient the line names that the product does not contain
    missing = _missing_named_ingredients(medicine, named)
    if missing:
        add("ingredient", "conflict", f"The line names {', '.join(sorted(missing))}, which “{name}” does not contain.")

    # release type
    line_release = detect_line_release(raw_text)
    if line_release and medicine.get("release_type") != line_release:
        add("release", "conflict", f"The line says {line_release.upper()} (a modified-release product), but “{name}” is not that release type.")

    # a number the product does not own; a name that spells the brand out explains its own numbers
    if not exact:
        numbers = _unexplained_numbers(raw_text, medicine)
        if numbers:
            hint = ""
            if any(_SCHEDULE_LOOKALIKE_RE.match(n) for n in numbers):
                hint = " If it is the dose schedule (for example 1-0-0 read as 100) rather than a strength, you can ignore this."
            add("number", "conflict", f"The number {', '.join(numbers)} on the line is not a strength of “{name}”.{hint}")

    # facts about the chosen product that change what the analysis can say
    if medicine.get("composition_incomplete"):
        add("incomplete_composition", "note", "The dataset's ingredient list for this product is incomplete, so no alternatives are compared.")
    if medicine.get("is_discontinued"):
        add("discontinued", "note", "The dataset marks this product as discontinued.")
    return findings


def _without_schedule_digits(raw_text):
    """
    (text without the three digits that look like a dose schedule, those digits) - or (raw_text, None) when there are none.
    Handwritten "1-0-0" very often comes back as "100", which then reads as a strength. Only digits that stand alone AFTER a
    name are considered ("Tab Dolo 100", never "100 mg" or a leading number).
    """
    match = instruction_service.DIGITS_RUN_RE.search(raw_text or "")
    if not match or not any(c != "0" for c in match.group(1)):
        return raw_text, None
    if not re.search(r"[A-Za-z]{3,}", (raw_text or "")[:match.start()]):
        return raw_text, None
    stripped = ((raw_text or "")[:match.start()] + " " + (raw_text or "")[match.end():]).strip()
    return re.sub(r"\s{2,}", " ", stripped), match.group(1)


def match_line(raw_text):
    """
    The outcome for one OCR line (see _match_line_once), with one extra step for handwriting.

    Handwritten "1-0-0" very often comes back as "100" and is then read as a strength, which can push the right product out of
    the candidates altogether ("T. pan - D 100": the top guess was a look-alike that merely contained "100"). When a line is
    NOT settled and has three such digits after its name, the line is read again without them, and if that second reading
    settles on a product whose name carries no number of its own and which does not own that number as a strength, that product
    is put FIRST among the candidates, with the reason.

    It never settles the line: the status stays "needs_verification". The number written on the line is exactly what the
    product contradicts, so only the person can say whether it was a schedule. The result carries "ignored_schedule_digits".
    """
    result = _match_line_once(raw_text)
    if result["status"] != "needs_verification":
        return result
    alt, digits = _without_schedule_digits(raw_text)
    if not digits:
        return result
    retry = _match_line_once(alt)
    candidate = retry.get("medicine")
    if retry["status"] != "matched" or not candidate:
        return result
    if re.search(r"\d", candidate.get("medicine_name") or "") or digits in instruction_service.owned_numbers(candidate):
        return result

    entry = _option_entry(retry["confidence"], candidate)
    entry["reasons"] = [
        f"Without the number {digits} this product fits the name. {digits} may be a dose schedule ({'-'.join(digits)}) read as digits, "
        "not a strength, but this product has no such strength, so only you can say.",
    ] + _guess_reasons(raw_text, retry["confidence"], candidate)[1:]
    others = [g for g in (result.get("guesses") or []) if g["medicine_id"] != candidate["medicine_id"]]
    return {
        **result, "raw_text": raw_text, "medicine": candidate, "confidence": round(retry["confidence"], 4),
        "guesses": ([entry] + others)[:MAX_OPTIONS], "ignored_schedule_digits": digits,
    }


def _match_line_once(raw_text):
    """
    Returns a dict describing the outcome for one OCR line:
      {
        "raw_text": ...,
        "status": "matched" | "needs_verification" | "skipped",
        "confidence": float or None,
        "medicine": <candidate dict> or None,
      }
    "skipped" means the line had no medicine-like content at all (no
    FULLTEXT candidates whatsoever, or every word was filtered out as
    administrative/instructional/specialty vocabulary) - e.g. a patient
    name, a date, or "Cardiology" - so no Prescription_Medicines row
    should be created for it.
    """
    if _is_document_furniture(raw_text) or not _has_substantive_word(raw_text):
        return {"raw_text": raw_text, "status": "skipped", "confidence": None, "medicine": None}

    query = _build_boolean_query(raw_text)
    candidates = search_candidates(query) if query else []

    # Two retrieval routes, because they fail in opposite directions:
    # FULLTEXT is spelling-tolerant and finds things by salt, but buries an
    # exact brand under its generic equivalents; the prefix lookup finds the
    # written brand exactly but can't tolerate a typo. Scoring still decides.
    by_id = {c["medicine_id"]: c for c in candidates}
    for row in search_by_name_prefix(_prefix_lookup_words(raw_text)):
        by_id.setdefault(row["medicine_id"], row)
    candidates = list(by_id.values())

    if not candidates:
        return _unidentified_or_skipped(raw_text)

    cleaned_line = _clean_for_comparison(raw_text)
    named_ingredients = _named_ingredients(raw_text, candidates)
    line_release = detect_line_release(raw_text)
    scored = []
    for c in candidates:
        score, threshold, disqualified = _score_candidate(
            raw_text, cleaned_line, c, named_ingredients=named_ingredients, line_release=line_release
        )
        scored.append((score, threshold, disqualified, c))
    scored.sort(key=lambda row: row[0], reverse=True)

    # A disqualified candidate (confirmed strength/form conflict) must
    # never block a different, genuinely eligible candidate from being
    # considered just because it happened to score higher on text alone -
    # so pick the best ELIGIBLE candidate for the "matched" decision, not
    # just the single highest-scoring row overall.
    eligible = [row for row in scored if not row[2] and row[0] >= row[1]]
    eligible = [row for row in eligible if _settles_automatically(raw_text, row[0], row[3], named_ingredients)]
    if eligible:
        # Every candidate here already cleared its bar, so this only decides
        # WHICH good match wins. One that accounts for every token the line
        # wrote beats one that merely scores well on string overlap: for
        # "Zerodol-P", "Zerodol-P Tablet" explains the trailing "P" and
        # "Zerodol Gel" does not. Ties fall back to score, as before.
        # Combination products the line didn't ask for are dropped outright
        # whenever a single-ingredient (or explicitly named) candidate
        # exists - "unless no exact match exists" - not merely demoted.
        plain_eligible = [row for row in eligible if not _is_unmentioned_combination(raw_text, row[3])]
        if plain_eligible:
            eligible = plain_eligible

        # A line that states no release type is not asking for a modified-release
        # product. Among candidates that are otherwise equally good (within the
        # disambiguation margin of the best score) a conventional product beats a
        # sustained/extended/... one. This is a tie-break, deliberately NOT a
        # filter: filtering removed the only product whose strength agreed with
        # the line ("Glycomet 500" would have become "Glycomet 250"). A brand that
        # is only sold as SR still matches.
        top_score = max(row[0] for row in eligible)

        def rank(row):
            candidate = row[3]
            return (
                not _covers_every_token(raw_text, candidate["medicine_name"]),
                _is_unmentioned_combination(raw_text, candidate),
                (not line_release) and is_modified(candidate.get("release_type")) and row[0] >= top_score - DISAMBIGUATION_MARGIN,
                _form_mismatch(raw_text, candidate["form"]),   # prefer the form the line implies
                -row[0],
                candidate["medicine_id"],                       # stable among exact ties
            )

        eligible.sort(key=rank)
        best_score, _, _, best_candidate = eligible[0]

        # Under-specified line (no strength / form the dataset could not contradict):
        # several different medicines still fit, so do not pick one.
        variants, resolved_generic, preferred = _ambiguous_variants(
            raw_text, cleaned_line, best_candidate, best_score, eligible, named_ingredients, line_release
        )
        # The one medicine this generic line means is a different release type from the product the
        # text search happened to rank first: use the one the line means. (Never the other way round:
        # a line that states SR was already limited to SR products.)
        if preferred and preferred[1].get("release_type") != best_candidate.get("release_type"):
            best_score, best_candidate = preferred
        if variants:
            return {
                "raw_text": raw_text,
                "status": "needs_verification",
                "confidence": None,
                "medicine": None,
                "needs_disambiguation": True,
                "options": variants,
            }

        # Several equally good, genuinely different medicines? Then the line
        # does not say which one was meant, and picking silently is a guess.
        best_covers = _covers_every_token(raw_text, best_candidate["medicine_name"])
        options = [_option_entry(best_score, best_candidate)]
        seen = {_signature(best_candidate)}
        for score, _, _, candidate in eligible[1:]:
            if len(options) >= MAX_OPTIONS or score < best_score - DISAMBIGUATION_MARGIN:
                continue
            if _covers_every_token(raw_text, candidate["medicine_name"]) != best_covers:
                continue
            if _form_mismatch(raw_text, candidate["form"]):
                continue
            signature = _signature(candidate)
            if signature in seen:
                continue
            seen.add(signature)
            options.append(_option_entry(score, candidate))

        return {
            "raw_text": raw_text,
            "status": "matched",
            "confidence": round(best_score, 4),
            "medicine": best_candidate,
            "needs_disambiguation": len(options) >= 2 and not resolved_generic,
            "options": options if len(options) >= 2 and not resolved_generic else [],
        }

    # No eligible match. Offer the best candidate as a transparent "closest
    # guess" - but only if it is close enough to be worth offering at all.
    # A product missing an ingredient the line names ("Amoxicillin + Clavulanic
    # acid" -> plain amoxycillin) is a different medicine, so it is not even
    # offered as a guess.
    def contradicts_strength(candidate):
        stated = _per_ingredient_agreement(raw_text, candidate, named_ingredients)
        if stated is None:
            stated = _combination_strength_agreement(raw_text, candidate)
        return stated == 0.0

    def number_points_elsewhere(candidate):
        return _unexplained_number(raw_text, candidate) and not _covers_every_token(raw_text, candidate["medicine_name"])

    guessable = [
        row for row in scored
        if not _missing_named_ingredients(row[3], named_ingredients) and not contradicts_strength(row[3])
        and not number_points_elsewhere(row[3])
    ]
    if not guessable:
        return _unidentified_or_skipped(raw_text)
    best_score, best_threshold, best_disqualified, best_candidate = guessable[0]
    if best_score >= MIN_GUESS_SCORE:
        return {
            "raw_text": raw_text,
            "status": "needs_verification",
            "confidence": round(best_score, 4),
            "medicine": best_candidate,  # closest guess only - NOT confirmed, caller must label it as such
            # the closest look-alikes with why each was not accepted: stored so the person can review them
            "guesses": _closest_guesses(raw_text, guessable),
        }
    return _unidentified_or_skipped(raw_text)
