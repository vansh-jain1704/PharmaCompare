import os
import shutil
import tempfile

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from app.models.medicine_model import get_medicine_by_id
from app.services import data_validation_service, image_quality_service, scan_service
from app.services.cloud_ocr_service import redact_secrets, redacted_traceback
from app.services.composition import display_strength
from app.services.ocr_service import extract_text
from app.services.release_type import RELEASE_LABELS

scan_bp = Blueprint("scan", __name__)

SCAN_EXTENSIONS = {"jpg", "jpeg", "png"}


def _medicine_payload(candidate):
    """The same fields the medicine search returns, so the details drawer works on a scan result unchanged."""
    m = get_medicine_by_id(candidate["medicine_id"])
    if not m:
        return None
    return {
        "medicine_id": m["medicine_id"], "medicine_name": m["medicine_name"], "composition": m["composition"], "form": m["form"],
        "strength": m["strength"], "display_strength": display_strength(m["composition"], m["strength"]),
        "manufacturer": m["manufacturer"], "pack_size": m["pack_size"], "price": float(m["price"]) if m["price"] is not None else None,
        "is_discontinued": bool(m["is_discontinued"]), "release_type": m.get("release_type"),
        "release_label": RELEASE_LABELS.get(m.get("release_type"), "modified release") if m.get("release_type") else None,
        "composition_incomplete": bool(m.get("composition_incomplete")),
        "data_notes": data_validation_service.validate_medicine(m),
        # why it was offered, and that nothing about it is confirmed
        "score": candidate["score"], "from_line": candidate["from_line"], "settled_by_reader": candidate["settled_by_reader"],
        "reasons": candidate["reasons"],
    }


@scan_bp.route("/api/medicines/scan", methods=["POST"])
@jwt_required()
def scan_medicine():
    """
    Reads a photo of a medicine pack and returns the products its text could mean, best first. It NEVER confirms a product (`confirmed` is
    always false) and stores nothing: the photo is processed from a temporary file that is deleted before the response is sent.
    """
    if "file" not in request.files or request.files["file"].filename == "":
        return jsonify({"error": "no file selected"}), 400
    file = request.files["file"]
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in SCAN_EXTENSIONS:
        return jsonify({"error": "unsupported file type", "allowed_types": sorted(SCAN_EXTENSIONS)}), 400

    folder = tempfile.mkdtemp(prefix="pharmacompare_scan_")
    path = os.path.join(folder, f"pack.{ext}")
    try:
        file.save(path)
        quality = image_quality_service.assess(path, ext)
        try:
            result = extract_text(path, ext)
        except Exception as exc:
            current_app.logger.error("OCR failed while scanning a medicine pack: %s", redacted_traceback(exc))
            return jsonify({"error": "OCR processing failed", "details": redact_secrets(exc)}), 500
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    if not result["readable"]:
        return jsonify({"message": "the photo is too unclear to read reliably", "confirmed": False, "candidates": [], "image_quality": quality}), 422

    candidates = [p for p in (_medicine_payload(c) for c in scan_service.candidates_from_lines(result["lines"])) if p]
    return jsonify({
        "confirmed": False,
        "notice": scan_service.NOTICE,
        "candidates": candidates,
        "lines": result["lines"],
        "ocr_provider": result.get("provider"),
        "image_quality": quality,
        "message": None if candidates else "Nothing on file matches the text read from this pack. Try the medicine search, or a clearer photo of the front of the pack.",
    }), 200
