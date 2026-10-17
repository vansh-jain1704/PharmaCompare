"""
Clinical Decision Engine - a self-contained safety-analysis layer that runs
after Medicine Detection. Designed to be imported independently by future
modules (Price Comparison, Generic Recommendation, Availability) without
any coupling to the prescription upload route.

Hard safety rules enforced here (not just documented - see the code):
  - Never invents an interaction: interaction findings only ever come from
    a real Drug_Interactions (DDInter 2.0) row.
  - Never claims a combination is "safe": an uncovered/unknown pair is
    always reported as NEEDS_VERIFICATION, never omitted or marked safe.
  - Never diagnoses, never tells the user to stop/start/change a medicine:
    every non-trivial finding's recommendation is to consult a doctor or
    pharmacist, worded identically everywhere in this file.
  - Every finding distinguishes confirmed database information (DDInter
    row, our own Medicines row, our own Prescription_Medicines row) from
    system-generated analysis (the rollup risk_level and summary).
  - Only ever analyzes medicines Medicine Detection actually confirmed
    (match_status == 'matched') - never runs safety logic against an
    unconfirmed OCR guess.
"""
import re
from itertools import combinations

from app.models.medicine_model import get_prescription_medicines
from app.services.match_status import is_confirmed
from app.models.prescription_model import get_prescription_by_id, list_prescriptions_by_user
from app.models.safety_model import (
    clear_findings,
    find_interaction,
    is_salt_covered,
    save_finding,
    save_analysis_summary,
)
from app.models.user_model import get_user_allergies
from app.services.allergy_service import check_medicine_against_allergies

DOCTOR_ADVICE = "This is not a diagnosis. Please verify with your doctor or pharmacist before acting on it."

SALT_FORM_SUFFIXES = {
    "acetate", "hydrochloride", "sulfate", "sulphate", "sodium", "potassium",
    "citrate", "besylate", "maleate", "dimaleate", "mesylate", "tartrate",
    "phosphate", "succinate", "fumarate", "chloride", "bromide", "nitrate",
    "gluconate", "lactate", "carbonate", "bicarbonate", "dihydrate",
    "monohydrate", "trihydrate", "hydrobromide", "besilate", "camsylate",
    "napadisilate", "palmitate", "propionate", "valerate", "decanoate",
    "hemihydrate", "anhydrous", "disodium", "calcium", "magnesium",
}

STRENGTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|ml|gm?|iu|%)", re.IGNORECASE)

# Worst-to-least-informative, used to roll many findings up into one
# overall AI_Analysis.risk_level. Higher number = more severe/important.
SEVERITY_RANK = {"Major": 4, "Moderate": 3, "Minor": 2, "Unknown": 1, "NEEDS_VERIFICATION": 0}

INTERACTION_SOURCE = "DDInter 2.0 (ddinter2.scbdd.com)"
LOCAL_SOURCE = "PharmaCompare local analysis (Medicines/Prescription_Medicines records)"
ALLERGY_SOURCE_NONE = "none - no allergies declared on this account"
ALLERGY_SOURCE_NO_MEDICINE = "none - no medicine on this prescription is confirmed yet"
ALLERGY_SOURCE = "allergies declared by the account holder, matched by name against recorded salts"


# The medicine dataset uses Indian/British drug names, DDInter uses USAN/INN
# ones. Same substance, different spelling - and DDInter holds NOTHING under
# the former (checked against Drug_Interactions: "paracetamol" 0 rows,
# "acetaminophen" 274), so without this every paracetamol or amoxycillin line
# was reported as "not covered" when its data was simply filed under the
# other name. Only pairs verified to have DDInter rows under the target name
# are listed.
SALT_NAME_ALIASES = {
    "paracetamol": "acetaminophen",
    "amoxycillin": "amoxicillin",
    "adrenaline": "epinephrine",
    "frusemide": "furosemide",
    "aspirin": "acetylsalicylic acid",
    "glibenclamide": "glyburide",
    "lignocaine": "lidocaine",
    # Added after auditing every ingredient in the dataset against the DDInter
    # table. Each pair is the SAME active substance under another spelling,
    # synonym or salt form, and each target was confirmed to exist in
    # Drug_Interactions. Substances DDInter simply does not hold (aceclofenac,
    # domperidone, nimesulide, etoricoxib, ambroxol, ...) are deliberately NOT
    # mapped to anything: that would invent coverage.
    "cefalexin": "cephalexin",
    "methylcobalamin": "mecobalamin",
    "divalproex": "valproic acid",
    "valproate": "valproic acid",              # "Sodium Valproate" once "sodium" is stripped
    "beclometasone": "beclomethasone dipropionate",
    "niacinamide": "nicotinamide",
    "thyroxine": "levothyroxine",
    "aluminium hydroxide": "aluminum hydroxide",
    "xylometazoline": "xylometazoline (nasal)",  # DDInter files it by route
    "paracetamol/acetaminophen": "acetaminophen",
    "vitamin b6": "pyridoxine",
    "vitamin d3": "vitamin d",                 # cholecalciferol
    # Salt forms and bracketed qualifiers, listed one by one rather than stripped
    # generically. A generic rule broke "Azilsartan medoxomil" (DDInter holds it
    # under that full name) and would have mapped "Levonorgestrel (intrauterine
    # system)" onto the oral drug's interactions.
    "cefpodoxime proxetil": "cefpodoxime",
    "escitalopram oxalate": "escitalopram",
    "olmesartan medoxomil": "olmesartan",
    "progesterone (natural micronized)": "progesterone",
    "vitamin b6 (pyridoxine)": "pyridoxine",
    "doxorubicin (plain)": "doxorubicin",
}


def _normalize_salt(name):
    if not name:
        return ""
    words = name.lower().split()
    kept = [w for w in words if w not in SALT_FORM_SUFFIXES]
    normalised = " ".join(kept) if kept else name.lower()
    return SALT_NAME_ALIASES.get(normalised, normalised)


def _medicine_ref(pm_row):
    return {"medicine_id": pm_row["medicine_id"], "medicine_name": pm_row["medicine_name"]}


def _confirmed_medicines(prescription_medicines):
    """Only medicines Medicine Detection actually confirmed - never run
    safety analysis on a 'needs_verification' or unmatched OCR line, since
    we don't reliably know what medicine (if any) it actually is."""
    return [pm for pm in prescription_medicines if is_confirmed(pm["match_status"]) and pm["medicine_id"]]


def check_interactions(confirmed):
    """
    Checks every pair of distinct confirmed medicines against DDInter.
    Every pair produces exactly one finding - either a real interaction
    (severity from DDInter, verbatim) or NEEDS_VERIFICATION. No pair is
    ever silently skipped: absence of data must stay visible, never be
    implied as "no interaction" / "safe".
    """
    findings = []
    for pm_a, pm_b in combinations(confirmed, 2):
        salt_a, salt_b = pm_a.get("primary_salt"), pm_b.get("primary_salt")
        if not salt_a or not salt_b or salt_a.strip().lower() == salt_b.strip().lower():
            continue  # same-salt pairs are handled by check_duplicates, not here

        norm_a, norm_b = _normalize_salt(salt_a), _normalize_salt(salt_b)
        row = find_interaction(salt_a.strip().lower(), salt_b.strip().lower()) \
            or find_interaction(norm_a, norm_b)

        medicines_involved = [_medicine_ref(pm_a), _medicine_ref(pm_b)]

        if row:
            severity = row["severity"]  # Major | Moderate | Minor | Unknown - verbatim from DDInter
            if severity == "Unknown":
                explanation = (
                    f"DDInter 2.0 records that {salt_a} and {salt_b} are known to interact, "
                    f"but does not specify a severity level for this pair."
                )
            else:
                explanation = (
                    f"DDInter 2.0 records a {severity.upper()}-level interaction between "
                    f"{salt_a} and {salt_b}."
                )
            findings.append({
                "issue_type": "interaction",
                "medicines_involved": medicines_involved,
                "severity": severity,
                "confidence": 1.0,  # confirmed database record, not a guess
                "explanation": explanation,
                "recommendation": f"Do not combine or discontinue these medicines yourself. {DOCTOR_ADVICE}",
                "data_source": INTERACTION_SOURCE,
            })
        else:
            covered = is_salt_covered(salt_a.strip().lower()) or is_salt_covered(norm_a)
            covered_b = is_salt_covered(salt_b.strip().lower()) or is_salt_covered(norm_b)
            if covered and covered_b:
                explanation = (
                    f"No specific interaction record was found between {salt_a} and {salt_b} in "
                    f"DDInter 2.0, although both substances are individually tracked by it. "
                    f"This does NOT confirm the combination is safe - it may simply not be "
                    f"catalogued for this specific pair."
                )
            else:
                explanation = (
                    f"One or both of {salt_a} and {salt_b} are not covered by our interaction "
                    f"data source at all, so no interaction check could be performed."
                )
            findings.append({
                "issue_type": "interaction",
                "medicines_involved": medicines_involved,
                "severity": "NEEDS_VERIFICATION",
                "confidence": None,
                "explanation": explanation,
                "recommendation": f"{DOCTOR_ADVICE}",
                "data_source": INTERACTION_SOURCE,
            })
    return findings


def check_duplicates(confirmed):
    """
    Flags when the same active salt appears more than once among the
    confirmed medicines - a purely factual, local check (no external
    data). Never assigns a clinical severity to this fact (duplicate
    therapy can be intentional or accidental) - always NEEDS_VERIFICATION.
    """
    by_salt = {}
    for pm in confirmed:
        salt = (pm.get("primary_salt") or "").strip().lower()
        if not salt:
            continue
        by_salt.setdefault(salt, []).append(pm)

    findings = []
    for salt, rows in by_salt.items():
        if len(rows) < 2:
            continue
        findings.append({
            "issue_type": "duplicate",
            "medicines_involved": [_medicine_ref(pm) for pm in rows],
            "severity": "NEEDS_VERIFICATION",
            "confidence": 1.0,  # the duplication itself is a confirmed fact from our own records
            "explanation": (
                f"{len(rows)} medicines in this prescription share the same active ingredient "
                f"({rows[0]['primary_salt']}): "
                + ", ".join(pm["medicine_name"] for pm in rows) + "."
            ),
            "recommendation": f"Duplicate therapy may be intentional or accidental. {DOCTOR_ADVICE}",
            "data_source": LOCAL_SOURCE,
        })
    return findings


def check_dosage_consistency(prescription_medicines):
    """
    Compares the strength mentioned in the original OCR line against the
    strength recorded for the medicine it was matched to. Only flags a
    clear numeric disagreement - never asserts a dose is clinically
    excessive (we have no authoritative dosing-limit data for that).
    """
    findings = []
    for pm in prescription_medicines:
        if not is_confirmed(pm["match_status"]) or not pm["medicine_id"]:
            continue
        line_match = STRENGTH_RE.search(pm["raw_text"] or "")
        cand_match = STRENGTH_RE.search(pm["strength"] or "")
        if not line_match or not cand_match:
            continue
        if line_match.group(1) == cand_match.group(1):
            continue  # they agree - no finding needed, this isn't an "everything is fine" claim, just nothing to flag

        findings.append({
            "issue_type": "dosage_inconsistency",
            "medicines_involved": [_medicine_ref(pm)],
            "severity": "NEEDS_VERIFICATION",
            "confidence": pm["match_confidence"],
            "explanation": (
                f"The prescription text says \"{pm['raw_text']}\" (mentions "
                f"{line_match.group(1)}{line_match.group(2)}), but the matched product "
                f"\"{pm['medicine_name']}\" is recorded as {pm['strength']}. This may be an "
                f"OCR reading error, a different pack strength, or a genuine prescribing detail."
            ),
            "recommendation": f"Confirm the intended strength before dispensing or taking this medicine. {DOCTOR_ADVICE}",
            "data_source": LOCAL_SOURCE,
        })
    return findings


def check_allergies(prescription_id, confirmed):
    """
    Compares the account holder's declared allergies with each confirmed
    medicine's recorded salts. This is a NAME match (plus the penicillin,
    sulfa and NSAID groups) - it can raise an alert, but silence from it is
    not a clearance, and the wording says so.

      - nothing declared  -> one NEEDS_VERIFICATION finding saying the check
                             could not be done, and where to add allergies
      - declared, matched -> one Major finding per matching medicine
      - declared, no match-> one NEEDS_VERIFICATION finding stating what was
                             compared and that it is not a guarantee
    """
    # Nothing is confirmed, so NO safety check ran - not just this one. Say that, rather than blaming
    # the account's allergy list: with or without allergies declared there was nothing to compare.
    if not confirmed:
        return [{
            "issue_type": "allergy_check",
            "medicines_involved": [],
            "severity": "NEEDS_VERIFICATION",
            "confidence": None,
            "explanation": (
                "No medicine on this prescription has been confirmed yet, so the interaction, duplicate "
                "and allergy checks have not run. Confirm each medicine (use Verify on its row) and the "
                "checks will run on it."
            ),
            "recommendation": (
                "Please check each line against your original prescription, and tell your doctor or "
                f"pharmacist about any known drug allergies. {DOCTOR_ADVICE}"
            ),
            "data_source": ALLERGY_SOURCE_NO_MEDICINE,
        }]

    prescription = get_prescription_by_id(prescription_id) or {}
    allergies = get_user_allergies(prescription.get("user_id")) if prescription.get("user_id") else []

    if not allergies:
        return [{
            "issue_type": "allergy_check",
            "medicines_involved": [],
            "severity": "NEEDS_VERIFICATION",
            "confidence": None,
            "explanation": (
                "No allergies are declared on this account, so an allergy check could not be "
                "performed. You can add any known drug allergies under Profile, Health preferences."
            ),
            "recommendation": f"Please tell your doctor or pharmacist about any known drug allergies. {DOCTOR_ADVICE}",
            "data_source": ALLERGY_SOURCE_NONE,
        }]

    findings = []
    for pm in confirmed:
        hit = check_medicine_against_allergies(pm, allergies)
        if hit:
            findings.append({
                "issue_type": "allergy_check",
                "medicines_involved": [_medicine_ref(pm)],
                "severity": "Major",
                "confidence": 1.0,
                "explanation": hit["text"],
                "recommendation": f"Do not take this medicine until you have spoken to your doctor or pharmacist. {DOCTOR_ADVICE}",
                "data_source": ALLERGY_SOURCE,
            })

    if not findings:
        findings.append({
            "issue_type": "allergy_check",
            "medicines_involved": [],
            "severity": "NEEDS_VERIFICATION",
            "confidence": None,
            "explanation": (
                f"You declared: {', '.join(allergies)}. None of the identified medicines matched "
                "by name or by medicine group. This only compares names and a few common groups, "
                "so it is not a guarantee."
            ),
            "recommendation": f"Still mention your allergies to your doctor or pharmacist. {DOCTOR_ADVICE}",
            "data_source": ALLERGY_SOURCE,
        })
    return findings


def _rollup_summary(findings, confirmed_count):
    if not findings:
        return "NEEDS_VERIFICATION", "No medicines were confidently identified in this prescription, so no safety analysis could be performed."

    worst = max(findings, key=lambda f: SEVERITY_RANK.get(f["severity"], 0))
    real_interactions = [f for f in findings if f["issue_type"] == "interaction" and f["severity"] != "NEEDS_VERIFICATION"]
    duplicates = [f for f in findings if f["issue_type"] == "duplicate"]
    dosage_issues = [f for f in findings if f["issue_type"] == "dosage_inconsistency"]

    parts = [f"Analyzed {confirmed_count} confirmed medicine(s) in this prescription."]
    if real_interactions:
        parts.append(f"{len(real_interactions)} known interaction(s) found in DDInter 2.0.")
    if duplicates:
        parts.append(f"{len(duplicates)} duplicate active-ingredient finding(s).")
    if dosage_issues:
        parts.append(f"{len(dosage_issues)} dosage/strength inconsistency finding(s).")
    parts.append(DOCTOR_ADVICE)

    return worst["severity"], " ".join(parts)


def run_clinical_decision_engine(prescription_id):
    """
    Orchestrates the full engine for one prescription: fetches confirmed
    medicines, runs every check, persists each finding plus one rollup
    AI_Analysis summary row, and returns everything for the API response.
    Safe to call on a prescription with zero confirmed medicines - it
    will just report that no analysis could be performed, not error out.
    """
    prescription_medicines = get_prescription_medicines(prescription_id)
    confirmed = _confirmed_medicines(prescription_medicines)

    findings = []
    findings.extend(check_interactions(confirmed))
    findings.extend(check_duplicates(confirmed))
    findings.extend(check_dosage_consistency(prescription_medicines))
    findings.extend(check_allergies(prescription_id, confirmed))

    for f in findings:
        save_finding(
            prescription_id,
            f["issue_type"],
            f["medicines_involved"],
            f["severity"],
            f["confidence"],
            f["explanation"],
            f["recommendation"],
            f["data_source"],
        )

    risk_level, summary = _rollup_summary(findings, len(confirmed))
    save_analysis_summary(prescription_id, summary, risk_level)

    return {"risk_level": risk_level, "summary": summary, "findings": findings}


def refresh_user_analyses(user_id):
    """
    Re-runs the clinical analysis for every prescription a user has. Called
    when their allergies change, so stored findings never keep saying "no
    allergies declared" (or keep flagging one that was removed). Pure database
    work, so it is quick even for a long history.
    """
    refreshed = 0
    for prescription in list_prescriptions_by_user(user_id):
        clear_findings(prescription["prescription_id"])
        run_clinical_decision_engine(prescription["prescription_id"])
        refreshed += 1
    return refreshed
