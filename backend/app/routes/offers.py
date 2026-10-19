from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from app.models.medicine_model import get_medicine_by_id
from app.services import offer_service, price_provenance_service

offers_bp = Blueprint("offers", __name__)


@offers_bp.route("/api/medicines/<int:medicine_id>/offers", methods=["GET"])
@jwt_required()
def medicine_offers(medicine_id):
    """
    What pharmacies have REPORTED for one medicine: price, stock and when, with the feed each report came from. A medicine
    nobody has reported on returns count 0 and "not reported": nothing is estimated and the dataset price is not used here.
    """
    medicine = get_medicine_by_id(medicine_id)
    if not medicine:
        return jsonify({"error": "medicine not found"}), 404
    described = offer_service.offers_for_medicines([medicine_id]).get(medicine_id) or offer_service.describe([])
    return jsonify({
        "medicine_id": medicine_id, "medicine_name": medicine["medicine_name"], **described,
        # what the dataset's reference price for this product is, and how old that snapshot is (never a live price)
        "price_basis": price_provenance_service.reference_basis(medicine.get("imported_at")),
    }), 200
