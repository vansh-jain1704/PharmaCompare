from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models.prescription_model import get_prescription_by_id
from app.services.price_comparison_service import get_annotated_price_comparison

price_comparison_bp = Blueprint("price_comparison", __name__)


@price_comparison_bp.route("/api/prescriptions/<int:prescription_id>/prices", methods=["GET"])
@jwt_required()
def get_prescription_prices(prescription_id):
    user_id = get_jwt_identity()
    prescription = get_prescription_by_id(prescription_id)

    if not prescription or str(prescription["user_id"]) != str(user_id):
        return jsonify({"error": "prescription not found"}), 404

    rows = get_annotated_price_comparison(prescription_id)

    # Regroup the flat stored rows back into one entry per prescribed
    # medicine with its alternatives nested - the same shape the upload
    # response returns, so a client can treat both the same way.
    by_pm = {}
    for row in rows:
        pm_id = row["pm_id"]
        entry = by_pm.setdefault(pm_id, {"pm_id": pm_id, "raw_text": row["raw_text"], "prescribed": None, "alternatives": []})
        if row["row_type"] == "prescribed":
            entry["prescribed"] = row
        else:
            entry["alternatives"].append(row)

    return jsonify({
        "prescription_id": prescription_id,
        "medicines": list(by_pm.values()),
    }), 200
