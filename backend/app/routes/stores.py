from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.services import store_locator_service as locator

stores_bp = Blueprint("stores", __name__)

# This blueprint is an independent, location-only feature: it imports nothing about medicines, prescriptions, prices or stock.
#
# Both routes take POST with a JSON body, not GET with a query string: a position or a place name in a URL is written to web-server
# access logs, and this feature promises that the person's location is not logged.


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@stores_bp.route("/api/stores/nearby", methods=["POST"])
@jwt_required()
def nearby_stores():
    """
    Medical stores and Jan Aushadhi Kendras near a position, as OpenStreetMap lists them (not verified; see the response's
    verification_note). The position is rounded to about 100 m, used for this request only and never stored or logged.
    Body: lat, lon (required); radius_km; scope = all (default) | jan_aushadhi (Kendras only) | generic (Kendras and generic stores) | pharmacy (the others).
    """
    body = _body()
    try:
        result = locator.search_nearby(body.get("lat"), body.get("lon"), body.get("radius_km"), body.get("scope") or "all")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except locator.PlacesNotConfigured as exc:
        return jsonify({"error": str(exc), "configured": False}), 503
    except locator.PlacesUnavailable as exc:
        return jsonify({"error": str(exc)}), 503
    return jsonify(result), 200


@stores_bp.route("/api/stores/geocode", methods=["POST"])
@jwt_required()
def find_place():
    """Turns a typed place name or PIN code into positions, for people who do not share their location. Only when asked. Body: q."""
    try:
        return jsonify(locator.geocode(_body().get("q"))), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except locator.PlacesNotConfigured as exc:
        return jsonify({"error": str(exc), "configured": False}), 503
    except locator.PlacesUnavailable as exc:
        return jsonify({"error": str(exc)}), 503
