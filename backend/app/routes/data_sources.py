from flask import Blueprint, jsonify

from app.services import data_sources_service

data_sources_bp = Blueprint("data_sources", __name__)


@data_sources_bp.route("/api/data-sources", methods=["GET"])
def list_data_sources():
    """
    The registry of data PharmaCompare uses: what each source is, its size, when it was obtained, the licence AS RECORDED
    (null when not recorded) and a quality note counted from the live tables. Public: nothing here is personal.
    """
    return jsonify({"sources": data_sources_service.list_sources(), "live_data": data_sources_service.live_data(),
                    "external_services": data_sources_service.external_services()}), 200
