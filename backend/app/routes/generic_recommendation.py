from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models.prescription_model import get_prescription_by_id
from app.models.recommendation_model import get_recommendations

generic_recommendation_bp = Blueprint("generic_recommendation", __name__)


@generic_recommendation_bp.route("/api/prescriptions/<int:prescription_id>/recommendations", methods=["GET"])
@jwt_required()
def get_prescription_recommendations(prescription_id):
    user_id = get_jwt_identity()
    prescription = get_prescription_by_id(prescription_id)

    if not prescription or str(prescription["user_id"]) != str(user_id):
        return jsonify({"error": "prescription not found"}), 404

    rows = get_recommendations(prescription_id)

    by_pm = {}
    for row in rows:
        entry = by_pm.setdefault(row["pm_id"], {"pm_id": row["pm_id"], "raw_text": row["raw_text"], "recommendations": []})
        entry["recommendations"].append(row)

    return jsonify({
        "prescription_id": prescription_id,
        "medicines": list(by_pm.values()),
    }), 200
