"""
The plain-language summary at the top of the Smart Health Report (the PPT's "AI-powered smart health report").

Two writers behind one function, and the reader is always told which one wrote it:

  * Google Gemini, when GEMINI_API_KEY is set. It is given a short list of FACTS and nothing else, and its answer is used only if it
    passes the checks below;
  * PharmaCompare itself otherwise, from the same facts, so the summary works with no key, no network and no cost.

WHAT IS SENT: medicine names, strengths, forms, schedules, durations, and counts. NEVER the patient's name, the image, the original OCR
text, an allergen's name, or any free text from the prescription. (An allergy appears only as "N line(s) carry an allergy alert".)

WHY IT IS FENCED IN: a generated paragraph in a medicines app can quietly cross into advice. So the answer is accepted only when
  - every number in it appears in the facts (no invented strength, price, count or duration). This catches a number that is ABSENT from the
    facts; it cannot catch an allowed number used in a wrong sense, which is why it is one of several checks and why "take" is forbidden too;
  - it uses none of the words of advice, assurance or diagnosis ("safe", "should take", "stop", "switch to", "cure", ...);
  - it mentions everything the facts flag (lines to check, lines not identified, allergy alerts, safety findings);
  - it is short.
Anything else is thrown away and the deterministic summary is used. The wording is never trusted to a model alone.
"""
import logging
import re

import requests

from app.config import Config
from app.services.medicine_explainer_service import _redact, _redacted_traceback

logger = logging.getLogger(__name__)

MAX_CHARS = 900
LABEL_GEMINI = ("Written by Google Gemini from the figures in this report (medicine names, strengths, schedules and counts only). "
                "It can be wrong: check it against the report.")
LABEL_LOCAL = "Written by PharmaCompare from the figures in this report."

SYSTEM_RULES = (
    "You write a short plain-language summary of a prescription analysis for the patient. Use ONLY the facts given. "
    "Do not add any medicine, number, price, dose, strength or duration that is not in the facts. "
    "Do not give medical advice, do not say anything is safe or unsafe, do not say what to take, stop, start or switch, and do not diagnose. "
    "You must mention every line that needs the patient's check, every line that is not identified, every allergy alert and every safety finding listed. "
    "Say that prices are reference prices from a dataset snapshot, not live pharmacy prices. At most 120 words, in simple sentences."
)

# words of advice, assurance or diagnosis the summary must never contain
FORBIDDEN = re.compile(
    r"\b(safe|safely|unsafe|should (?:take|stop|start|switch|avoid|use)|must (?:take|stop|start|switch)|stop(?:ped|ping)? taking|"
    r"tak(?:e|es|en|ing)|"
    r"start(?:ed|ing)? taking|switch(?:ed|ing)? to|replace (?:it|them|your)|recommend(?:s|ed)? (?:that )?you|cure[sd]?|diagnos\w*|treat(?:s|ment of)\b|"
    r"no (?:risk|interaction|danger)|harmless)\b",
    re.IGNORECASE,
)
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# "Rs 93.50", "Rs. 93", "₹93.50" and "93.50 rupees"
RUPEES = re.compile(r"(?:Rs\.?|₹)\s*(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s*rupees?", re.IGNORECASE)


def _normalise_number(token):
    """'93.50', '93.5' and '93.500' are one number; '1,000' is 1000."""
    token = token.replace(",", "")
    try:
        value = float(token)
    except ValueError:
        return token
    return str(int(value)) if value == int(value) else repr(value)


def numbers_in(text):
    return {_normalise_number(t) for t in NUMBER.findall(text or "")}


def build_facts(data):
    """The facts of one report (from smart_report_service.collect_report_data), and nothing that identifies the patient."""
    identified, not_identified, to_check, allergy_alerts = [], 0, 0, 0
    for ln in data["lines"]:
        sf, pm = ln["safety"], ln["pm"]
        if sf.get("allergy_alert"):
            allergy_alerts += 1
        if ln["status"] == "Not identified (by you)":
            not_identified += 1
            continue
        if not ln["identified"]:
            not_identified += 1
            continue
        if ln["status"] == "Check match":
            to_check += 1
        ins = sf.get("instructions") or {}
        identified.append({
            "name": pm["medicine_name"], "strength": sf.get("display_strength") or pm.get("strength"), "form": pm.get("form"),
            "status": ln["status"], "schedule": ins.get("text"), "duration": ins.get("duration"),
        })
    findings = data.get("findings") or []
    severities = {}
    for f in findings:
        severities[f["severity"]] = severities.get(f["severity"], 0) + 1
    return {
        "lines": data["detected"], "identified": identified, "not_identified": not_identified, "to_check": to_check,
        "allergy_alerts": allergy_alerts, "findings": len(findings), "finding_severities": severities,
        "saving": data["total_saving"], "saving_counted_on": data["counted_for_savings"], "original_total": data["original_total"],
        "has_pharmacy_reports": bool(data.get("offers")),
    }


def facts_text(facts):
    lines = [f"Lines read from the prescription: {facts['lines']}.", f"Identified medicines: {len(facts['identified'])}."]
    if facts["identified"]:
        for m in facts["identified"]:
            bits = [m["name"], m["strength"], m["form"], f"status: {m['status']}"]
            if m["schedule"]:
                bits.append(f"as written: {m['schedule']}")
            if m["duration"]:
                bits.append(f"for {m['duration']}")
            lines.append("- " + "; ".join(str(b) for b in bits if b))
    lines.append(f"Lines that need the patient's check: {facts['to_check']}.")
    lines.append(f"Lines not identified: {facts['not_identified']}.")
    lines.append(f"Lines with an allergy alert: {facts['allergy_alerts']}.")
    sev = ", ".join(f"{n} {name}" for name, n in sorted(facts["finding_severities"].items())) or "none"
    lines.append(f"Safety findings: {facts['findings']} ({sev}).")
    if facts["saving"] and facts["saving"] > 0:
        lines.append(f"Reference-price saving counted: Rs {facts['saving']:.2f} of Rs {facts['original_total']:.2f} across {facts['saving_counted_on']} medicine(s).")
    else:
        lines.append("No reference-price saving is counted.")
    lines.append("Pharmacy price or stock reports exist." if facts["has_pharmacy_reports"] else "No pharmacy has reported a price or stock.")
    return "\n".join(lines)


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def deterministic_summary(facts):
    """The same facts in plain sentences, written locally. It uses none of the forbidden words."""
    parts = [f"{_plural(facts['lines'], 'line')} {'was' if facts['lines'] == 1 else 'were'} read from the prescription."]
    if facts["identified"]:
        names = ", ".join(m["name"] for m in facts["identified"])
        parts.append(f"{_plural(len(facts['identified']), 'medicine')} {'is' if len(facts['identified']) == 1 else 'are'} identified: {names}.")
    else:
        parts.append("No medicine is identified yet.")
    if facts["to_check"]:
        parts.append(f"{_plural(facts['to_check'], 'line')} need{'s' if facts['to_check'] == 1 else ''} your check against the prescription.")
    if facts["not_identified"]:
        parts.append(f"{_plural(facts['not_identified'], 'line')} {'is' if facts['not_identified'] == 1 else 'are'} not identified and not part of the checks.")
    if facts["allergy_alerts"]:
        parts.append(f"{_plural(facts['allergy_alerts'], 'line')} {'carries' if facts['allergy_alerts'] == 1 else 'carry'} an allergy alert: see the safety section.")
    if facts["findings"]:
        sev = ", ".join(f"{n} {name.lower()}" for name, n in sorted(facts["finding_severities"].items()))
        parts.append(f"The safety check recorded {_plural(facts['findings'], 'finding')} ({sev}); ask your pharmacist about them.")
    else:
        parts.append("The safety check recorded no findings, which is not a guarantee: interaction data does not cover every medicine.")
    if facts["saving"] and facts["saving"] > 0:
        parts.append(f"Cheaper same-ingredient options could lower the reference price by Rs {facts['saving']:.2f} across {_plural(facts['saving_counted_on'], 'medicine')}; "
                     "these are reference prices from a dataset snapshot, not live pharmacy prices.")
    else:
        parts.append("No saving is counted; prices are reference prices from a dataset snapshot, not live pharmacy prices.")
    return " ".join(parts)


def validate(text, facts):
    """(True, None) when a generated summary may be used, else (False, why)."""
    if not text or not text.strip():
        return False, "empty"
    if len(text) > MAX_CHARS:
        return False, "too long"
    if FORBIDDEN.search(text):
        return False, f"uses a forbidden word ({FORBIDDEN.search(text).group(0)!r})"
    invented = numbers_in(text) - numbers_in(facts_text(facts)) - {"0"}
    if invented:
        return False, f"states numbers that are not in the facts: {sorted(invented)}"
    # a strength or a count in the facts must not be passed off as a price: a rupee amount may only be one of the report's own totals
    allowed_amounts = [float(facts["saving"] or 0), float(facts["original_total"] or 0)]
    for match in RUPEES.finditer(text):
        amount = float((match.group(1) or match.group(2)).replace(",", ""))
        if not any(abs(amount - a) < 0.005 for a in allowed_amounts):
            return False, f"states a rupee amount that is not one of the report's totals ({amount:g})"
    lowered = text.lower()
    # a medicine may be left out of a short summary, but a flag may not
    if facts["allergy_alerts"] and "allerg" not in lowered:
        return False, "leaves out the allergy alert"
    if facts["to_check"] and "check" not in lowered:
        return False, "leaves out the lines that need checking"
    if facts["not_identified"] and "not identified" not in lowered and "unidentified" not in lowered:
        return False, "leaves out the lines that are not identified"
    if facts["findings"] and not re.search(r"finding|interaction", lowered):
        return False, "leaves out the safety findings"
    if "reference" not in lowered:
        return False, "does not say the prices are reference prices"
    return True, None


def _ask_gemini(facts):
    endpoint = f"{Config.GEMINI_ENDPOINT}/models/{Config.GEMINI_MODEL}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_RULES}]},
        "contents": [{"role": "user", "parts": [{"text": f"Facts:\n{facts_text(facts)}\n\nWrite the summary."}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300},
    }
    try:
        response = requests.post(endpoint, params={"key": Config.GEMINI_API_KEY}, json=payload, timeout=Config.LLM_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise RuntimeError(f"could not reach Gemini ({type(exc).__name__}): {_redact(exc)}") from None
    if response.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {_redact(response.text[:200])}")
    candidates = response.json().get("candidates") or []
    parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
    return "".join(p.get("text", "") for p in parts).strip()


def is_configured():
    return bool(Config.GEMINI_API_KEY)


def summarise(data):
    """
    {"text", "source": "gemini" | "local", "label", "rejected": reason or None}. Never raises: a summary failing is no reason to withhold the report.
    """
    facts = build_facts(data)
    rejected = None
    if is_configured():
        try:
            text = _ask_gemini(facts)
            ok, why = validate(text, facts)
            if ok:
                return {"text": text, "source": "gemini", "label": LABEL_GEMINI, "rejected": None}
            rejected = why
            logger.warning("Gemini summary rejected (%s); using the local summary", why)
        except Exception as exc:
            rejected = "the Gemini request failed"
            logger.error("Gemini summary failed; using the local summary: %s", _redacted_traceback(exc))
    return {"text": deterministic_summary(facts), "source": "local", "label": LABEL_LOCAL, "rejected": rejected}
