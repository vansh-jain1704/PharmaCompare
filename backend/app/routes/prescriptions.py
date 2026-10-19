import json
import os
import re
import uuid

from flask import Blueprint, request, jsonify, current_app, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from mysql.connector import Error as MySQLError

from app.models.prescription_model import (
    create_prescription,
    update_prescription_status,
    get_prescription_by_id,
    list_prescriptions_by_user,
    save_ocr_result,
    get_ocr_result_by_prescription,
    delete_prescription,
)
from app.models.medicine_model import (
    save_prescription_medicine,
    get_prescription_medicines,
    search_medicines_with_mode,
    update_prescription_medicine_match,
    mark_prescription_medicine_unmatched,
    save_user_entered_details,
    get_prescription_medicine,
    delete_prescription_medicine,
    get_medicine_by_id,
)
from app.models import verification_log_model
from app.models.safety_model import get_findings, get_analysis_summary, clear_findings
from app.models.price_model import clear_price_comparison
from app.models.recommendation_model import get_recommendations, clear_recommendations
from app.services.ocr_service import extract_text
from app.services.cloud_ocr_service import redact_secrets, redacted_traceback
from app.services.release_type import RELEASE_LABELS
from app.services.medicine_matching_service import match_line, assess_confirmation, MANUAL_ENTRY_TEXT
from app.services.dosage_parser import parse_dosage, parse_duration, parse_frequency, parse_instructions
from app.services import data_sources_service, data_validation_service, image_quality_service, instruction_service, price_provenance_service, manual_entry_service, offer_service, prescription_notes_service, report_summary_service, timeline_service
from app.services.smart_report_service import build_report_pdf, collect_report_data, prescription_title, report_path_for
from app.services import medicine_explainer_service, medicine_safety_service
from app.models.user_model import get_user_allergies
from app.models.report_model import save_report
from app.services.clinical_decision_service import run_clinical_decision_engine
from app.services.price_comparison_service import run_price_comparison, get_annotated_price_comparison
from app.services.generic_recommendation_service import run_generic_recommendations
from app.config import Config

prescriptions_bp = Blueprint("prescriptions", __name__)

MAX_NAME_LENGTH = 255
MAX_RAW_TEXT_LENGTH = 500  # matches Prescription_Medicines.raw_text
MAX_SYMPTOMS_JSON_LENGTH = 5000  # generous but bounded, this is user-typed selections, not a file

# Mirrors frontend/src/data/symptoms.js PRESCRIPTION_TYPES - kept in sync
# manually since this is plain metadata, not something driving logic.
ALLOWED_PRESCRIPTION_TYPES = {
    "General Physician", "Dental", "Eye / Ophthalmology", "ENT",
    "Dermatology / Skin", "Orthopedic", "Cardiology", "Neurology",
    "Gynecology", "Pediatrics", "Other", "Not Sure",
}


def _parse_symptoms_field():
    """
    Returns (symptoms_dict_or_None, error_message_or_None).
    The symptoms field is purely user-selected context - we store it as-is,
    we never interpret or act on it here.
    """
    raw = request.form.get("symptoms")
    if not raw:
        return None, None
    if len(raw) > MAX_SYMPTOMS_JSON_LENGTH:
        return None, "symptoms data is too large"
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None, "symptoms must be valid JSON"
    if not isinstance(parsed, dict):
        return None, "symptoms must be a JSON object"
    return parsed, None


def _allowed_file(filename):
    if "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[1].lower()
    return ext if ext in Config.ALLOWED_EXTENSIONS else None


def _options_to_store(result):
    """
    What goes in Prescription_Medicines.match_options for one matcher result: the several close matches a
    person must choose between, or - for a line that could only be matched to look-alikes - those look-alikes
    with the reasons they were not accepted, so the Verify screen can show them later. Never a confirmation.
    """
    if result.get("needs_disambiguation"):
        return result.get("options")
    if result.get("guesses"):
        return {"kind": medicine_safety_service.CLOSEST_GUESSES_KIND, "candidates": result["guesses"]}
    return None


def _run_medicine_detection(prescription_id, ocr_lines):
    """
    Runs Medicine Detection over every OCR line and records the outcome.
    A line is only ever recorded as a confirmed medicine when it clears
    the matching engine's confidence threshold; otherwise it's stored as
    'needs_verification' so nothing gets silently presented as fact. Lines
    with no medicine-like content at all (patient name, date, etc.) are
    skipped entirely - never stored as a fake "medicine".
    """
    detected = []
    results = []
    for line in ocr_lines:
        text = line["text"].strip()
        if not text:
            continue
        result = match_line(text)
        if result["status"] == "skipped":
            continue
        results.append((text, result))

    # Dosing is often written BELOW the name and comes back as a separate OCR line ("T Lincont 100" / "x30dys"): an
    # instruction-only line is attached to the medicine line above it. Only what the prescription states is read.
    attached = instruction_service.attach([text for text, _ in results], ocr_lines, lambda t: True)

    for text, result in results:
        medicine = result["medicine"]
        medicine_id = medicine["medicine_id"] if result["status"] == "matched" else None
        merged = attached.get(text, {}).get("instructions") or instruction_service.parse(text)
        if medicine_id:                       # digits that are really the product's own strength are not a schedule
            merged = instruction_service.drop_schedule_that_is_a_strength(merged, instruction_service.owned_numbers(medicine))
        dosage, frequency, duration = instruction_service.to_columns(merged)
        # the plain-English patterns, as before (only these: parse_instructions also carries the reading above)
        old_dosage, old_frequency, old_duration = parse_dosage(text), parse_frequency(text), parse_duration(text)
        dosage, frequency, duration = dosage or old_dosage, frequency or old_frequency, duration or old_duration
        pm_id = save_prescription_medicine(
            prescription_id,
            medicine_id,
            raw_text=result["raw_text"],
            match_confidence=result["confidence"],
            match_status=result["status"],
            dosage=dosage,
            frequency=frequency,
            duration=duration,
            match_options=_options_to_store(result),
        )
        detected.append({
            "pm_id": pm_id,
            "raw_text": result["raw_text"],
            "status": result["status"],
            "confidence": result["confidence"],
            "dosage": dosage,
            "frequency": frequency,
            "duration": duration,
            # The same fields the history endpoint returns. Sending a thinner
            # version here made the upload page claim "not on file" for a
            # manufacturer, pack size and price that are on file - the UI was
            # honestly reporting what it had been given, which is worse than
            # a blank: it reads as missing data rather than a missing field.
            "medicine": {
                "medicine_id": medicine["medicine_id"],
                "medicine_name": medicine["medicine_name"],
                "composition": medicine["composition"],
                "form": medicine["form"],
                "strength": medicine["strength"],
                "primary_salt": medicine.get("primary_salt"),
                "secondary_salt": medicine.get("secondary_salt"),
                "manufacturer": medicine.get("manufacturer"),
                "pack_size": medicine.get("pack_size"),
                "release_type": medicine.get("release_type"),
                "price": float(medicine["price"]) if medicine.get("price") is not None else None,
                "is_discontinued": bool(medicine["is_discontinued"]),
            } if medicine else None,
        })
    return detected


def _public_decision(decision):
    """The part of a stored verification decision the screen needs (who is implied: the signed-in owner)."""
    return {
        "decision": decision.get("decision"),
        "decided_at": decision.get("decided_at"),
        "medicine_id": decision.get("medicine_id"),
        "medicine_name": decision.get("medicine_name"),
        "warnings_acknowledged": bool(decision.get("warnings_acknowledged")),
        "warnings": decision.get("warnings") or [],
        "previous_status": decision.get("previous_status"),
        "raw_text": decision.get("raw_text"),
    }


def _stored_suggestions(pm_row):
    """The candidates a line was carrying when a person decided on it, as [{medicine_id, medicine_name, score}]."""
    raw = pm_row.get("match_options")
    try:
        decoded = raw if isinstance(raw, (list, dict)) else json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return []
    if isinstance(decoded, dict):
        decoded = decoded.get("candidates")
    return [{"medicine_id": o.get("medicine_id"), "medicine_name": o.get("medicine_name"), "score": o.get("score")}
            for o in (decoded or []) if isinstance(o, dict)]


def _log_verification(user_id, prescription_id, pm_row, decision, medicine=None, **extra):
    """Records one decision in the review trail. A failure here is logged, never hidden from the response."""
    try:
        verification_log_model.log_decision(
            int(user_id), prescription_id, pm_row["pm_id"] if pm_row else extra.pop("pm_id", None), decision,
            raw_text=pm_row["raw_text"] if pm_row else extra.pop("raw_text", None),
            medicine_id=medicine["medicine_id"] if medicine else None,
            medicine_name=medicine["medicine_name"] if medicine else None,
            previous_status=pm_row["match_status"] if pm_row else None,
            previous_confidence=float(pm_row["match_confidence"]) if pm_row and pm_row.get("match_confidence") is not None else None,
            suggestions=_stored_suggestions(pm_row) if pm_row else [],
            **extra,
        )
        return True
    except Exception:
        current_app.logger.exception("Could not record the verification decision for prescription %s", prescription_id)
        return False


def _allergy_check(user_id):
    """What the allergy check had to work with (see medicine_safety_service.allergy_check_status)."""
    return medicine_safety_service.allergy_check_status(get_user_allergies(user_id))


def _attach_safety(entries, prescription_id, user_id):
    """
    Adds the per-medicine safety fields (interaction status, verification
    status, allergy alert, close-match options) to each response entry,
    keyed by pm_id. Derived fresh on every response - see
    medicine_safety_service for why nothing here is stored.
    """
    rows = get_prescription_medicines(prescription_id)
    ocr = get_ocr_result_by_prescription(prescription_id) or {}
    annotations = medicine_safety_service.annotate(rows, get_user_allergies(user_id), ocr.get("line_results") or [])
    identified_ids = [e.get("medicine_id") if e.get("medicine_id") is not None else (e.get("medicine") or {}).get("medicine_id")
                      for e in entries if (e.get("match_status") or e.get("status")) in ("matched", "user_confirmed")]
    offers = offer_service.offers_for_medicines(identified_ids)
    history = {}
    for decision in verification_log_model.get_decisions(prescription_id):
        history.setdefault(decision.get("pm_id"), []).append(_public_decision(decision))
    for entry in entries:
        entry.update(annotations.get(entry.get("pm_id"), {}))
        past = history.get(entry.get("pm_id"), [])
        mid = entry.get("medicine_id") if entry.get("medicine_id") is not None else (entry.get("medicine") or {}).get("medicine_id")
        entry["offers"] = offers.get(mid) if (entry.get("match_status") or entry.get("status")) in ("matched", "user_confirmed") else None
        entry["verification_history"] = past                                   # every decision on this line, oldest first
        entry["verification_decision"] = past[-1] if past else None            # the latest one
    return entries


@prescriptions_bp.route("/api/prescriptions/upload", methods=["POST"])
@jwt_required()
def upload_prescription():
    user_id = get_jwt_identity()

    if "file" not in request.files:
        return jsonify({"error": "no file part in the request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "no file selected"}), 400

    ext = _allowed_file(file.filename)
    if not ext:
        return jsonify({
            "error": "unsupported file type",
            "allowed_types": sorted(Config.ALLOWED_EXTENSIONS),
        }), 400

    prescription_name = (request.form.get("prescription_name") or "").strip()
    if len(prescription_name) > MAX_NAME_LENGTH:
        return jsonify({"error": f"prescription name must be at most {MAX_NAME_LENGTH} characters"}), 400
    prescription_name = prescription_name or None  # let it fall back to a generated label later

    prescription_type = (request.form.get("prescription_type") or "").strip() or None
    if prescription_type and prescription_type not in ALLOWED_PRESCRIPTION_TYPES:
        return jsonify({
            "error": "invalid prescription type",
            "allowed_types": sorted(ALLOWED_PRESCRIPTION_TYPES),
        }), 400

    symptoms, symptoms_error = _parse_symptoms_field()
    if symptoms_error:
        return jsonify({"error": symptoms_error}), 400

    user_folder = os.path.join(Config.UPLOAD_FOLDER, str(user_id))
    os.makedirs(user_folder, exist_ok=True)

    stored_filename = f"{uuid.uuid4().hex}.{ext}"
    stored_path = os.path.join(user_folder, stored_filename)
    file.save(stored_path)

    try:
        prescription_id = create_prescription(
            user_id, stored_path,
            prescription_name=prescription_name,
            prescription_type=prescription_type,
            symptoms=symptoms,
            status="uploaded",
        )
    except MySQLError as e:
        os.remove(stored_path)
        return jsonify({"error": "database error", "details": str(e)}), 500

    quality = image_quality_service.assess(stored_path, ext)        # warnings only: never blocks, never changes the OCR

    try:
        result = extract_text(stored_path, ext)
    except Exception as e:
        update_prescription_status(prescription_id, "processing_failed")
        # message and traceback as before, but never with the cloud API key in them
        current_app.logger.error("OCR processing failed for prescription %s: %s", prescription_id, redacted_traceback(e))
        return jsonify({
            "error": "OCR processing failed",
            "details": redact_secrets(e),
            "prescription_id": prescription_id,
        }), 500

    # Which engine read this upload, how many lines it found, and whether the cloud engine failed and
    # EasyOCR took over. Counts and names only: never the prescription text, the account, or any key.
    current_app.logger.info(
        "OCR for prescription %s: provider=%s lines=%d fallback=%s readable=%s",
        prescription_id, result.get("provider"), len(result["lines"]), bool(result.get("fallback")), bool(result["readable"]),
    )

    if not result["readable"]:
        update_prescription_status(prescription_id, "needs_reupload")
        save_ocr_result(prescription_id, result["text"], result["confidence"], lines=result["lines"])
        return jsonify({
            "message": "prescription image is too unclear to read reliably",
            "prescription_id": prescription_id,
            "prescription_name": prescription_name,
            "prescription_type": prescription_type,
            "status": "needs_reupload",
            "confidence": result["confidence"],
            "image_quality": quality,
        }), 422

    update_prescription_status(prescription_id, "processed")
    save_ocr_result(prescription_id, result["text"], result["confidence"], lines=result["lines"])

    try:
        detected_medicines = _run_medicine_detection(prescription_id, result["lines"])
    except Exception:
        # Medicine Detection is a bonus layer on top of a successful OCR
        # result - if it fails, the user should still get their OCR text
        # rather than a 500 for the whole upload.
        current_app.logger.exception("Medicine detection failed for prescription %s", prescription_id)
        detected_medicines = []

    try:
        clinical_analysis = run_clinical_decision_engine(prescription_id)
    except Exception:
        # Same principle as Medicine Detection above: a Clinical Decision
        # Engine failure should not take down an otherwise-successful
        # upload+OCR+detection result.
        current_app.logger.exception("Clinical decision engine failed for prescription %s", prescription_id)
        clinical_analysis = None

    try:
        price_comparison = run_price_comparison(prescription_id)
    except Exception:
        current_app.logger.exception("Price comparison failed for prescription %s", prescription_id)
        price_comparison = []

    try:
        recommendations = run_generic_recommendations(price_comparison)
    except Exception:
        current_app.logger.exception("Generic recommendation failed for prescription %s", prescription_id)
        recommendations = []

    _attach_safety(detected_medicines, prescription_id, user_id)

    return jsonify({
        "message": "prescription uploaded and processed successfully",
        "prescription_id": prescription_id,
        "prescription_name": prescription_name,
        "prescription_type": prescription_type,
        "symptoms": symptoms,
        "status": "processed",
        "extracted_text": result["text"],
        "confidence": result["confidence"],
        "ocr_provider": result.get("provider"),
        "image_quality": quality,
        "lines": result["lines"],
        "notes": prescription_notes_service.notes_from_ocr_lines(result["lines"]),
        "live_data": data_sources_service.live_data(),
        "price_basis": price_provenance_service.dataset_basis(),
        "allergy_check": _allergy_check(user_id),
        "detected_medicines": detected_medicines,
        "timeline": timeline_service.build_timeline(timeline_service.entries_from_detected(detected_medicines)),
        "clinical_analysis": clinical_analysis,
        "price_comparison": price_comparison,
        "recommendations": recommendations,
    }), 201


@prescriptions_bp.route("/api/prescriptions", methods=["GET"])
@jwt_required()
def list_prescriptions():
    user_id = get_jwt_identity()
    rows = list_prescriptions_by_user(user_id)
    for row in rows:
        row["filename"] = os.path.basename(row["image_path"])
        del row["image_path"]
    return jsonify({"prescriptions": rows}), 200


@prescriptions_bp.route("/api/prescriptions/<int:prescription_id>", methods=["GET"])
@jwt_required()
def get_prescription(prescription_id):
    user_id = get_jwt_identity()
    prescription = get_prescription_by_id(prescription_id)

    if not prescription or str(prescription["user_id"]) != str(user_id):
        # identical response whether it doesn't exist or belongs to someone
        # else, so this endpoint can't be used to probe which IDs exist
        return jsonify({"error": "prescription not found"}), 404

    ocr_result = get_ocr_result_by_prescription(prescription_id)
    detected_medicines = _attach_safety(get_prescription_medicines(prescription_id), prescription_id, user_id)
    analysis_summary = get_analysis_summary(prescription_id)
    findings = get_findings(prescription_id)
    price_rows = get_annotated_price_comparison(prescription_id)
    recommendation_rows = get_recommendations(prescription_id)
    quality = image_quality_service.assess(prescription["image_path"], os.path.splitext(prescription["image_path"])[1].lstrip("."))
    prescription["filename"] = os.path.basename(prescription["image_path"])
    del prescription["image_path"]

    return jsonify({
        "prescription": prescription,
        "image_quality": quality,
        "ocr_result": ocr_result,
        "notes": prescription_notes_service.notes_from_ocr_lines((ocr_result or {}).get("line_results") or []),
        "live_data": data_sources_service.live_data(),
        "price_basis": price_provenance_service.dataset_basis(),
        "allergy_check": _allergy_check(user_id),
        "detected_medicines": detected_medicines,
        "timeline": timeline_service.build_timeline(timeline_service.entries_from_detected(detected_medicines)),
        "clinical_analysis": {
            "risk_level": analysis_summary["risk_level"] if analysis_summary else None,
            "summary": analysis_summary["summary"] if analysis_summary else None,
            "findings": findings,
        },
        "price_comparison": price_rows,
        "recommendations": recommendation_rows,
    }), 200


def _rerun_analysis(prescription_id):
    """
    Regenerates everything derived from the detected medicines. Each stage
    is cleared before it re-runs, so correcting a medicine replaces the old
    conclusions instead of stacking a second set on top of them.
    """
    clear_findings(prescription_id)
    clear_recommendations(prescription_id)
    clear_price_comparison(prescription_id)

    clinical_analysis = run_clinical_decision_engine(prescription_id)
    price_comparison = run_price_comparison(prescription_id)
    recommendations = run_generic_recommendations(price_comparison)
    return clinical_analysis, price_comparison, recommendations


@prescriptions_bp.route("/api/medicines/search", methods=["GET"])
@jwt_required()
def search_medicines():
    """
    Backs the "this isn't the right medicine" picker. Read-only lookup over
    the Medicines table - it reports what is on file and nothing more.
    """
    term = (request.args.get("q") or "").strip()
    if len(term) < 2:
        return jsonify({"medicines": [], "message": "type at least 2 characters"}), 200

    rows, used_fallback = search_medicines_with_mode(term)
    return jsonify({
        # True when nothing matched what was typed and these are only products whose names START the same way:
        # different medicines, which the screen must say so rather than present as matches
        "fallback": used_fallback,
        "fallback_note": (f"No product on file matches “{term}”. These are products whose names start with similar "
                          "letters - they are different medicines, so check each one carefully.") if used_fallback else None,
        "medicines": [{
            "medicine_id": r["medicine_id"],
            "medicine_name": r["medicine_name"],
            "composition": r["composition"],
            "form": r["form"],
            "strength": r["strength"],
            "manufacturer": r["manufacturer"],
            "pack_size": r["pack_size"],
            "price": float(r["price"]) if r["price"] is not None else None,
            "is_discontinued": bool(r["is_discontinued"]),
            # enough to tell products apart: a sustained-release tablet and a plain one share name, salt,
            # strength and form, and an incomplete ingredient list means the composition shown is partial
            "release_type": r.get("release_type"),
            "release_label": RELEASE_LABELS.get(r.get("release_type"), "modified release") if r.get("release_type") else None,
            "composition_incomplete": bool(r.get("composition_incomplete")),
            # where the product's own fields are missing or do not fit together (a reason to check, never a correction)
            "data_notes": data_validation_service.validate_medicine(r),
        } for r in rows],
        "count": len(rows),
    }), 200


@prescriptions_bp.route("/api/medicines/<int:medicine_id>/explain", methods=["GET"])
@jwt_required()
def explain_medicine(medicine_id):
    """
    Plain-language description of one medicine, generated from its stored
    record. Read-only: it never changes anything and never invents a
    medicine that isn't on file.
    """
    medicine = get_medicine_by_id(medicine_id)
    if not medicine:
        return jsonify({"error": "medicine not found"}), 404

    result = medicine_explainer_service.explain(medicine)
    return jsonify({
        "medicine_id": medicine_id,
        "medicine_name": medicine["medicine_name"],
        **result,
    }), 200


@prescriptions_bp.route("/api/prescriptions/<int:prescription_id>/medicines", methods=["POST"])
@jwt_required()
def add_medicine_manually(prescription_id):
    """
    Adds a medicine the user says is on the prescription.

    Needed because OCR can fail to produce ANY usable line for a medicine on
    a handwritten script - correcting a row only helps when a row exists.
    The line is recorded as user_confirmed with a raw_text that states it
    was entered by hand, so the results table never misrepresents it as
    something that was read off the image.
    """
    user_id = get_jwt_identity()
    prescription = get_prescription_by_id(prescription_id)
    if not prescription or str(prescription["user_id"]) != str(user_id):
        return jsonify({"error": "prescription not found"}), 404

    data = request.get_json(silent=True) or {}
    medicine_id = data.get("medicine_id")
    if not isinstance(medicine_id, int) or isinstance(medicine_id, bool):   # JSON true is a Python int 1
        return jsonify({"error": "medicine_id (integer) is required"}), 400

    medicine = get_medicine_by_id(medicine_id)
    if not medicine:
        return jsonify({"error": "medicine not found"}), 404

    dosage_text = (data.get("dosage_text") or "").strip()[:MAX_RAW_TEXT_LENGTH] or None
    dosage, frequency, duration = parse_instructions(dosage_text) if dosage_text else (None, None, None)

    pm_id = save_prescription_medicine(
        prescription_id,
        medicine_id,
        raw_text=dosage_text or MANUAL_ENTRY_TEXT,
        match_confidence=None,
        match_status="user_confirmed",
        dosage=dosage,
        frequency=frequency,
        duration=duration,
    )

    audit_logged = _log_verification(
        user_id, prescription_id, None, verification_log_model.DECISION_ADDED_MANUALLY, medicine,
        pm_id=pm_id, raw_text=dosage_text or MANUAL_ENTRY_TEXT, warnings=[], warnings_acknowledged=False,
    )

    try:
        _rerun_analysis(prescription_id)
    except Exception:
        current_app.logger.exception("Re-analysis failed after adding medicine to %s", prescription_id)
        return jsonify({
            "message": "medicine added, but re-analysis failed",
            "reanalysis_failed": True,
            "pm_id": pm_id,
        }), 201

    return jsonify({
        "message": "medicine added and analysis updated",
        "pm_id": pm_id,
        "medicine_id": medicine_id,
        "medicine_name": medicine["medicine_name"],
    }), 201


@prescriptions_bp.route(
    "/api/prescriptions/<int:prescription_id>/medicines/<int:pm_id>", methods=["PATCH"]
)
@jwt_required()
def correct_detected_medicine(prescription_id, pm_id):
    """
    Lets the user say what a detected line actually is, when OCR misread it
    or the matcher could not settle it. The line's own text is left
    exactly as it was read - only which medicine it points at changes - and
    the whole downstream analysis is regenerated from the correction.

    A choice that clearly conflicts with what the line says (a different name, form, strength, ingredient or
    release type) is NOT saved straight away: the response is 409 with the conflicts in plain language, and the
    person has to send the same request again with "acknowledge_warnings": true. Even then the line is only
    recorded as "confirmed by you" - never as proof that the product is the one written or medically equivalent.
    Every saved decision is written to the review trail.
    """
    user_id = get_jwt_identity()
    prescription = get_prescription_by_id(prescription_id)
    if not prescription or str(prescription["user_id"]) != str(user_id):
        return jsonify({"error": "prescription not found"}), 404

    pm_row = get_prescription_medicine(pm_id)
    if not pm_row or pm_row["prescription_id"] != prescription_id:
        return jsonify({"error": "prescription medicine not found"}), 404

    data = request.get_json(silent=True) or {}
    medicine_id = data.get("medicine_id")
    if not isinstance(medicine_id, int) or isinstance(medicine_id, bool):   # JSON true is a Python int 1
        return jsonify({"error": "medicine_id (integer) is required"}), 400

    medicine = get_medicine_by_id(medicine_id)
    if not medicine:
        return jsonify({"error": "medicine not found"}), 404

    findings = assess_confirmation(pm_row["raw_text"], medicine)
    conflicts = [f for f in findings if f["severity"] == "conflict"]
    acknowledged = data.get("acknowledge_warnings") is True
    if conflicts and not acknowledged:
        return jsonify({
            "error": "confirmation_needs_acknowledgement",
            "message": ("Please check this before confirming: the prescription line and the product you chose differ. "
                        "Confirming only records your decision - it does not show that the product is the one "
                        "written or that it is medically equivalent."),
            "pm_id": pm_id,
            "medicine_id": medicine_id,
            "medicine_name": medicine["medicine_name"],
            "warnings": findings,
        }), 409

    # The row's existence is already established above. Don't gate on the
    # UPDATE's affected-row count: MySQL reports rows CHANGED, not matched,
    # so re-confirming the same medicine legitimately affects 0 rows and
    # must still succeed rather than look like a missing record.
    update_prescription_medicine_match(pm_id, medicine_id)
    audit_logged = _log_verification(
        user_id, prescription_id, pm_row, verification_log_model.DECISION_CONFIRMED, medicine,
        warnings=findings, warnings_acknowledged=bool(conflicts and acknowledged),
    )

    try:
        _rerun_analysis(prescription_id)
    except Exception:
        # The correction itself is saved and correct; only the derived
        # analysis failed. Say so plainly rather than reporting success.
        current_app.logger.exception("Re-analysis failed after correcting pm %s", pm_id)
        return jsonify({
            "message": "medicine corrected, but re-analysis failed",
            "reanalysis_failed": True,
            "pm_id": pm_id,
            "audit_logged": audit_logged,
        }), 200

    return jsonify({
        "message": "medicine confirmed by you and analysis updated",
        "pm_id": pm_id,
        "medicine_id": medicine_id,
        "medicine_name": medicine["medicine_name"],
        "warnings": findings,
        "warnings_acknowledged": bool(conflicts and acknowledged),
        "audit_logged": audit_logged,
    }), 200


@prescriptions_bp.route(
    "/api/prescriptions/<int:prescription_id>/medicines/<int:pm_id>/unmatched", methods=["POST"]
)
@jwt_required()
def mark_medicine_unmatched(prescription_id, pm_id):
    """
    The person reviewed this line and says it is not a medicine PharmaCompare can identify (or not a medicine
    at all). The line keeps its OCR text and the candidates it was shown; it points at no product, so it is never
    analysed or priced, and anything derived from an earlier confirmation of it is removed.
    """
    user_id = get_jwt_identity()
    prescription = get_prescription_by_id(prescription_id)
    if not prescription or str(prescription["user_id"]) != str(user_id):
        return jsonify({"error": "prescription not found"}), 404

    pm_row = get_prescription_medicine(pm_id)
    if not pm_row or pm_row["prescription_id"] != prescription_id:
        return jsonify({"error": "prescription medicine not found"}), 404

    mark_prescription_medicine_unmatched(pm_id)
    audit_logged = _log_verification(
        user_id, prescription_id, pm_row, verification_log_model.DECISION_UNMATCHED, None,
        warnings=[], warnings_acknowledged=False,
    )

    try:
        _rerun_analysis(prescription_id)
    except Exception:
        current_app.logger.exception("Re-analysis failed after marking pm %s as not identified", pm_id)
        return jsonify({"message": "line marked as not identified, but re-analysis failed",
                        "reanalysis_failed": True, "pm_id": pm_id, "audit_logged": audit_logged}), 200

    return jsonify({"message": "line marked as not identified and analysis updated", "pm_id": pm_id,
                    "audit_logged": audit_logged}), 200


@prescriptions_bp.route(
    "/api/prescriptions/<int:prescription_id>/medicines/<int:pm_id>/details", methods=["POST"]
)
@jwt_required()
def enter_medicine_details(prescription_id, pm_id):
    """
    The person types in the medicine for a line the dataset cannot identify: name, strength, form, schedule and duration as they read
    them from the prescription. It is stored as "entered by you", points at no product, and is never priced, compared or safety-checked.
    The line keeps its OCR text and the look-alikes it was shown.
    """
    user_id = get_jwt_identity()
    prescription = get_prescription_by_id(prescription_id)
    if not prescription or str(prescription["user_id"]) != str(user_id):
        return jsonify({"error": "prescription not found"}), 404

    pm_row = get_prescription_medicine(pm_id)
    if not pm_row or pm_row["prescription_id"] != prescription_id:
        return jsonify({"error": "prescription medicine not found"}), 404

    try:
        details = manual_entry_service.validate(request.get_json(silent=True))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    save_user_entered_details(pm_id, manual_entry_service.merge_into_options(pm_row.get("match_options"), details), details["schedule"], details["duration"])
    audit_logged = _log_verification(
        user_id, prescription_id, pm_row, verification_log_model.DECISION_ENTERED_BY_USER, None,
        warnings=[], warnings_acknowledged=False, entered=details,
    )

    try:
        _rerun_analysis(prescription_id)
    except Exception:
        current_app.logger.exception("Re-analysis failed after details were entered for pm %s", pm_id)
        return jsonify({"message": "details saved, but re-analysis failed", "reanalysis_failed": True, "pm_id": pm_id, "audit_logged": audit_logged}), 200

    return jsonify({"message": "details saved and analysis updated", "pm_id": pm_id, "audit_logged": audit_logged}), 200


@prescriptions_bp.route("/api/prescriptions/<int:prescription_id>/verification-log", methods=["GET"])
@jwt_required()
def get_verification_log(prescription_id):
    """Every verification decision recorded for this prescription (what was decided, when, and what the person saw)."""
    user_id = get_jwt_identity()
    prescription = get_prescription_by_id(prescription_id)
    if not prescription or str(prescription["user_id"]) != str(user_id):
        return jsonify({"error": "prescription not found"}), 404
    decisions = verification_log_model.get_decisions(prescription_id)
    return jsonify({"prescription_id": prescription_id, "decisions": decisions, "count": len(decisions)}), 200


@prescriptions_bp.route(
    "/api/prescriptions/<int:prescription_id>/medicines/<int:pm_id>", methods=["DELETE"]
)
@jwt_required()
def remove_detected_medicine(prescription_id, pm_id):
    """
    Drops a detected line the user says is not a medicine.

    Surfacing every plausible line means some non-medicine text (clinical
    notes, a stray mark) reaches the table, because on mangled handwriting
    those are indistinguishable from a medicine. Rather than guess and lose
    real medicines, we show them and let the user clear what doesn't belong.
    """
    user_id = get_jwt_identity()
    prescription = get_prescription_by_id(prescription_id)
    if not prescription or str(prescription["user_id"]) != str(user_id):
        return jsonify({"error": "prescription not found"}), 404

    pm_row = get_prescription_medicine(pm_id)
    if not pm_row or pm_row["prescription_id"] != prescription_id:
        return jsonify({"error": "prescription medicine not found"}), 404

    delete_prescription_medicine(pm_id)

    try:
        _rerun_analysis(prescription_id)
    except Exception:
        current_app.logger.exception("Re-analysis failed after removing pm %s", pm_id)
        return jsonify({"message": "line removed, but re-analysis failed",
                        "reanalysis_failed": True, "pm_id": pm_id}), 200

    return jsonify({"message": "line removed and analysis updated", "pm_id": pm_id}), 200


@prescriptions_bp.route("/api/prescriptions/<int:prescription_id>/summary", methods=["GET"])
@jwt_required()
def report_summary(prescription_id):
    """
    The plain-language summary of this analysis, written by Gemini when it is set up and its answer passes the checks, otherwise by
    PharmaCompare from the same facts. The response always says which (`source`, `label`). Only medicine names, strengths, schedules
    and counts leave the server, and only when Gemini is configured.
    """
    user_id = get_jwt_identity()
    prescription = get_prescription_by_id(prescription_id)
    if not prescription or str(prescription["user_id"]) != str(user_id):
        return jsonify({"error": "prescription not found"}), 404
    data = collect_report_data(prescription_id, prescription)
    return jsonify({"prescription_id": prescription_id, **report_summary_service.summarise(data)}), 200


@prescriptions_bp.route("/api/prescriptions/<int:prescription_id>/report", methods=["GET"])
@jwt_required()
def download_smart_report(prescription_id):
    """
    Generates (or regenerates) the Smart Health Report PDF and sends it.

    Always rebuilt from the current stored results rather than served from
    cache, so a report can never contradict the analysis on screen after a
    user corrects a medicine.
    """
    user_id = get_jwt_identity()
    prescription = get_prescription_by_id(prescription_id)
    if not prescription or str(prescription["user_id"]) != str(user_id):
        return jsonify({"error": "prescription not found"}), 404

    output_path = report_path_for(prescription_id, user_id)
    try:
        build_report_pdf(prescription_id, prescription, output_path)
    except Exception:
        current_app.logger.exception("Smart report generation failed for prescription %s", prescription_id)
        return jsonify({"error": "could not generate the report"}), 500

    save_report(prescription_id, output_path)

    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", prescription_title(prescription)).strip("_")
    return send_file(
        output_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"PharmaCompare_Report_{safe_name or prescription_id}.pdf",
    )


@prescriptions_bp.route("/api/prescriptions/<int:prescription_id>", methods=["DELETE"])
@jwt_required()
def delete_prescription_route(prescription_id):
    user_id = get_jwt_identity()
    prescription = get_prescription_by_id(prescription_id)

    if not prescription or str(prescription["user_id"]) != str(user_id):
        # same "not found" response whether it doesn't exist or belongs to
        # someone else - matches every other endpoint in this file
        return jsonify({"error": "prescription not found"}), 404

    image_path = prescription["image_path"]
    deleted = delete_prescription(prescription_id)
    if not deleted:
        return jsonify({"error": "prescription not found"}), 404

    # best-effort file cleanup - the DB row is already gone, a leftover
    # file on disk isn't worth failing the request over
    try:
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
    except OSError:
        current_app.logger.exception("Could not remove file for deleted prescription %s", prescription_id)

    return jsonify({"message": "prescription deleted", "prescription_id": prescription_id}), 200
