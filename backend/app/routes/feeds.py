from flask import Blueprint, jsonify, request

from app.config import Config
from app.models import partner_key_model
from app.services import partner_feed_service

feeds_bp = Blueprint("feeds", __name__)

# This route is for a pharmacy partner's own system, not for a person: it uses a partner key (X-Partner-Key), not a login. A missing, unknown,
# revoked or malformed key all get the same answer, so the route cannot be used to find out which keys exist.
UNAUTHORISED = {"error": "a valid partner key is required (X-Partner-Key header)"}


@feeds_bp.route("/api/feeds/offers", methods=["POST"])
def receive_offers():
    """
    A partner pushes price and stock reports: {"rows": [{"pharmacy", "city", "medicine_id" or "medicine_name" (+ "manufacturer", "pack_size"),
    "price", "availability", "quantity", "observed_at"}, ...], "dry_run": false}. Every row is validated exactly as a CSV feed is; rejected rows
    come back with the reason and nothing about them is stored. Reports are shown with their pharmacy, feed and age: this is not a live connection.
    """
    source = partner_key_model.find_active(request.headers.get("X-Partner-Key", ""))
    if not source or source["kind"] != "pharmacy_feed":
        return jsonify(UNAUTHORISED), 401
    if request.content_length is not None and request.content_length > Config.PARTNER_FEED_MAX_BYTES:
        return jsonify({"error": f"request is larger than {Config.PARTNER_FEED_MAX_BYTES} bytes"}), 413
    if partner_feed_service.too_many_requests(source["key_id"]):
        response = jsonify({"error": f"at most {Config.PARTNER_FEED_REQUESTS_PER_MINUTE} requests a minute for one key"})
        response.headers["Retry-After"] = "60"
        return response, 429

    body = request.get_json(silent=True)
    dry_run = isinstance(body, dict) and body.get("dry_run") is True
    try:
        report = partner_feed_service.ingest(source, body, dry_run=dry_run)
    except partner_feed_service.FeedRejected as exc:
        return jsonify({"error": str(exc)}), 400
    partner_key_model.touch(source["key_id"])
    return jsonify(report), 200
