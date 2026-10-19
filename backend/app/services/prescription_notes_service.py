"""
The lines of a prescription that are NOT medicines, shown beside the medicines instead of being dropped or mistaken for one.

  - Instructions for the patient or the nurse ("axillary temperature monitoring", "review after 1 week", "avoid cold drinks").
  - Notes written in Hindi ("सुबह खाने बाद"). They are shown exactly as read. A translation is offered only when every word is one of a few
    plain time-of-day / meal words, it is labelled as an automatic reading to check, and it is never attached to a medicine: the note
    does not say which medicine it belongs to.

Derived at read time from the stored OCR lines, like everything else in the analysis: nothing here is stored, and no stored row changes.
A line that starts like a medicine ("T.", "Tab", "Cap") is never a note, so a medicine is never hidden here.
"""
import re

DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
MEDICINE_PREFIX_RE = re.compile(r"^\s*(?:t|tab|tabs|tablet|cap|caps|tap|capsule|syp|syr|syrup|inj|injection|oint|ointment|drops?|gel|cream|susp)\b\.?\s", re.IGNORECASE)

# ACTION words that make an English line an instruction. Vitals words alone ("temperature", "BP", "sugar") are not here: a recorded
# reading is paperwork, "temperature monitoring" is an instruction because of "monitoring".
INSTRUCTION_WORDS = {
    "monitor", "monitoring", "review", "follow", "followup", "avoid", "rest", "diet", "fluids", "fluid", "drink", "exercise",
    "walk", "check", "checkup", "restrict", "gargle", "steam", "hydration",
}
HEADER_WORDS = {"medical", "advise", "advice"}

# Plain meal / time-of-day phrases. Anything outside this list gets no translation.
_PHRASES = [
    (re.compile(r"खाने\s*(?:के\s*)?बाद"), "after food"),
    (re.compile(r"खाने\s*(?:से\s*)?पहले"), "before food"),
    (re.compile(r"खाली\s*पेट"), "on an empty stomach"),
    (re.compile(r"सोने\s*(?:से\s*)?पहले"), "before sleeping"),
]
_WORDS = {"सुबह": "morning", "दोपहर": "afternoon", "शाम": "evening", "रात": "night"}


def hindi_meaning(text):
    """An English reading of a Hindi note made only of known meal / time-of-day words, or None. Always to be checked by the person."""
    remaining, parts = text, []
    for pattern, english in _PHRASES:
        if pattern.search(remaining):
            parts.append((pattern.search(remaining).start(), english))
            remaining = pattern.sub(" ", remaining)
    for word, english in _WORDS.items():
        index = remaining.find(word)
        if index >= 0:
            parts.append((index, english))
            remaining = remaining.replace(word, " ")
    leftover = [w for w in re.split(r"[\s,.:;|।\-]+", remaining) if w]
    if leftover or not parts:
        return None
    # keep the order they were written in only where it is known (phrases and words found above are ordered by their first position)
    return ", ".join(english for _, english in sorted(parts, key=lambda p: p[0]))


def notes_from_ocr_lines(lines):
    """
    [{"text", "kind": "hindi_note" | "instruction", "possible_meaning", "uncertain"}] for the non-medicine lines, in the order written.
    `lines` are the stored OCR lines ({"text", "confidence", "uncertain"}).
    """
    notes = []
    for line in lines or []:
        text = (line.get("text") or "").strip()
        if not text:
            continue
        uncertain = bool(line.get("uncertain"))
        if DEVANAGARI_RE.search(text):
            notes.append({"text": text, "kind": "hindi_note", "possible_meaning": hindi_meaning(text), "uncertain": uncertain})
            continue
        if MEDICINE_PREFIX_RE.match(text):
            continue
        words = [w.lower() for w in re.findall(r"[A-Za-z]+", text)]
        if not words or set(words) <= HEADER_WORDS:
            continue
        if any(w in INSTRUCTION_WORDS for w in words):
            notes.append({"text": text, "kind": "instruction", "possible_meaning": None, "uncertain": uncertain})
    return notes
