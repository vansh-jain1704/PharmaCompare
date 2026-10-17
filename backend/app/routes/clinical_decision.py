from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models.prescription_model import get_prescription_by_id
from app.models.safety_model import get_findings, get_analysis_summary

clinical_decision_bp = Blueprint("clinical_decision", __name__)


@clinical_decision_bp.route("/api/prescriptions/<int:prescription_id>/analysis", methods=["GET"])
@jwt_required()
def get_prescription_analysis(prescription_id):
    user_id = get_jwt_identity()
    prescription = get_prescription_by_id(prescription_id)

    if not prescription or str(prescription["user_id"]) != str(user_id):
        # same "not found" response whether it doesn't exist or belongs to
        # someone else, matching the rest of this API
        return jsonify({"error": "prescription not found"}), 404

    summary = get_analysis_summary(prescription_id)
    findings = get_findings(prescription_id)

    return jsonify({
        "prescription_id": prescription_id,
        "risk_level": summary["risk_level"] if summary else None,
        "summary": summary["summary"] if summary else None,
        "analysis_date": summary["analysis_date"] if summary else None,
        "findings": findings,
    }), 200
